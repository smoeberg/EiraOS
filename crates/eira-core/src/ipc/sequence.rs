//! Per-producer sequence tracking and explicit commit (Phase 0 §3.2–3.3).
//!
//! Life of one event at a consumer:
//!
//! ```text
//! receive → begin → complete → commit
//!             ↑         │
//!             └─ fail ──┘        (retry; the checkpoint never moves back)
//! ```
//!
//! Guarantees:
//!
//! * Nothing is committed implicitly. `commit(n)` commits exactly event `n`.
//! * Commits are sequential: `n` commits only after `n - 1`.
//! * Out-of-order events are buffered (bounded) and may be processed
//!   concurrently; only their commits are ordered.
//! * `CommitError::PredecessorPending` is not a processing failure. The
//!   consumer keeps its result and retries the commit after the predecessor
//!   has committed.
//!
//! Gaps: the Event Bus is at-most-once, so a predecessor may never arrive.
//! Strict sequential commit alone would then block that producer forever.
//! The consumer resolves this explicitly with [`SequenceTracker::declare_lost`],
//! which records the missing range and moves the checkpoint past it. It never
//! happens automatically, and it refuses to skip an event that was received.

use super::envelope::Id128;
use std::collections::{BTreeMap, HashMap};

/// Default bound on buffered, uncommitted events per producer.
pub const DEFAULT_MAX_PENDING: usize = 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Stage {
    Received,
    InFlight,
    Processed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Received {
    /// All predecessors are committed or buffered.
    InOrder,
    /// `missing` predecessors have not been received (yet, or ever).
    AfterGap { missing: u64 },
    /// Already committed or already buffered; must not be processed again.
    Duplicate,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SequenceError {
    InvalidSequence,
    BufferFull,
    NotReceived(u64),
    WrongStage(u64),
    /// `declare_lost` would skip an event that was actually received.
    ReceivedNotLost(u64),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CommitError {
    AlreadyCommitted(u64),
    NotReceived(u64),
    NotProcessed(u64),
    /// Retry after `expected` has committed (or been declared lost).
    PredecessorPending {
        expected: u64,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Gap {
    pub first: u64,
    pub last: u64,
}

#[derive(Debug, Clone)]
pub struct SequenceTracker {
    last_committed: u64,
    pending: BTreeMap<u64, Stage>,
    max_pending: usize,
    lost: u64,
}

impl Default for SequenceTracker {
    fn default() -> Self {
        Self::resume(0, DEFAULT_MAX_PENDING)
    }
}

impl SequenceTracker {
    /// Start from a persisted checkpoint (0 = nothing committed yet).
    pub fn resume(last_committed: u64, max_pending: usize) -> Self {
        Self {
            last_committed,
            pending: BTreeMap::new(),
            max_pending,
            lost: 0,
        }
    }

    pub fn checkpoint(&self) -> u64 {
        self.last_committed
    }

    /// Sequences declared lost since this tracker was created.
    pub fn lost(&self) -> u64 {
        self.lost
    }

    pub fn receive(&mut self, seq: u64) -> Result<Received, SequenceError> {
        if seq == 0 {
            return Err(SequenceError::InvalidSequence);
        }
        if seq <= self.last_committed || self.pending.contains_key(&seq) {
            return Ok(Received::Duplicate);
        }
        if self.pending.len() >= self.max_pending {
            return Err(SequenceError::BufferFull);
        }
        self.pending.insert(seq, Stage::Received);
        let between = seq - self.last_committed - 1;
        let buffered_before = self.pending.range(..seq).count() as u64;
        let missing = between - buffered_before;
        Ok(if missing == 0 {
            Received::InOrder
        } else {
            Received::AfterGap { missing }
        })
    }

    fn transition(&mut self, seq: u64, from: Stage, to: Stage) -> Result<(), SequenceError> {
        match self.pending.get_mut(&seq) {
            None => Err(SequenceError::NotReceived(seq)),
            Some(stage) if *stage == from => {
                *stage = to;
                Ok(())
            }
            Some(_) => Err(SequenceError::WrongStage(seq)),
        }
    }

    /// Processing of `seq` starts. Several events may be in flight at once.
    pub fn begin(&mut self, seq: u64) -> Result<(), SequenceError> {
        self.transition(seq, Stage::Received, Stage::InFlight)
    }

    /// Processing of `seq` finished successfully; it may now be committed.
    pub fn complete(&mut self, seq: u64) -> Result<(), SequenceError> {
        self.transition(seq, Stage::InFlight, Stage::Processed)
    }

    /// Processing of `seq` failed. The event stays buffered for a retry and
    /// the checkpoint is untouched.
    pub fn fail(&mut self, seq: u64) -> Result<(), SequenceError> {
        self.transition(seq, Stage::InFlight, Stage::Received)
    }

    /// Commit exactly `seq`. Only a processed event whose predecessor has
    /// committed can commit; nothing else moves.
    pub fn commit(&mut self, seq: u64) -> Result<(), CommitError> {
        if seq <= self.last_committed {
            return Err(CommitError::AlreadyCommitted(seq));
        }
        match self.pending.get(&seq) {
            None => return Err(CommitError::NotReceived(seq)),
            Some(Stage::Processed) => {}
            Some(_) => return Err(CommitError::NotProcessed(seq)),
        }
        let expected = self.last_committed + 1;
        if seq != expected {
            return Err(CommitError::PredecessorPending { expected });
        }
        self.pending.remove(&seq);
        self.last_committed = seq;
        Ok(())
    }

    /// Missing ranges between the checkpoint and the highest buffered event.
    pub fn gaps(&self) -> Vec<Gap> {
        let mut gaps = Vec::new();
        let mut next = self.last_committed + 1;
        for &seq in self.pending.keys() {
            if seq > next {
                gaps.push(Gap {
                    first: next,
                    last: seq - 1,
                });
            }
            next = seq + 1;
        }
        gaps
    }

    /// Explicitly accept that every sequence up to and including `through`
    /// that has not been received will never arrive. Refuses if any of them
    /// was received: those must be processed and committed normally.
    pub fn declare_lost(&mut self, through: u64) -> Result<u64, SequenceError> {
        if through <= self.last_committed {
            return Ok(0);
        }
        if let Some((&seq, _)) = self.pending.range(..=through).next() {
            return Err(SequenceError::ReceivedNotLost(seq));
        }
        let count = through - self.last_committed;
        self.last_committed = through;
        self.lost += count;
        Ok(count)
    }
}

/// Position of an event in its producer's stream.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct EventPosition {
    pub producer: Id128,
    pub sequence: u64,
}

/// Tracking for every producer a consumer listens to.
#[derive(Debug, Clone)]
pub struct ConsumerProgress {
    producers: HashMap<Id128, SequenceTracker>,
    max_pending: usize,
}

impl Default for ConsumerProgress {
    fn default() -> Self {
        Self::new(DEFAULT_MAX_PENDING)
    }
}

impl ConsumerProgress {
    pub fn new(max_pending: usize) -> Self {
        Self {
            producers: HashMap::new(),
            max_pending,
        }
    }

    /// Restore persisted checkpoints after a restart.
    pub fn resume(checkpoints: impl IntoIterator<Item = (Id128, u64)>, max_pending: usize) -> Self {
        let mut progress = Self::new(max_pending);
        for (producer, last) in checkpoints {
            progress
                .producers
                .insert(producer, SequenceTracker::resume(last, max_pending));
        }
        progress
    }

    fn tracker(&mut self, producer: Id128) -> &mut SequenceTracker {
        let max = self.max_pending;
        self.producers
            .entry(producer)
            .or_insert_with(|| SequenceTracker::resume(0, max))
    }

    fn existing(
        &mut self,
        producer: Id128,
        seq: u64,
    ) -> Result<&mut SequenceTracker, SequenceError> {
        self.producers
            .get_mut(&producer)
            .ok_or(SequenceError::NotReceived(seq))
    }

    pub fn receive(&mut self, at: EventPosition) -> Result<Received, SequenceError> {
        self.tracker(at.producer).receive(at.sequence)
    }

    pub fn begin(&mut self, at: EventPosition) -> Result<(), SequenceError> {
        self.existing(at.producer, at.sequence)?.begin(at.sequence)
    }

    pub fn complete(&mut self, at: EventPosition) -> Result<(), SequenceError> {
        self.existing(at.producer, at.sequence)?
            .complete(at.sequence)
    }

    pub fn fail(&mut self, at: EventPosition) -> Result<(), SequenceError> {
        self.existing(at.producer, at.sequence)?.fail(at.sequence)
    }

    pub fn commit(&mut self, at: EventPosition) -> Result<(), CommitError> {
        self.producers
            .get_mut(&at.producer)
            .ok_or(CommitError::NotReceived(at.sequence))?
            .commit(at.sequence)
    }

    pub fn declare_lost(&mut self, producer: Id128, through: u64) -> Result<u64, SequenceError> {
        self.tracker(producer).declare_lost(through)
    }

    pub fn gaps(&self, producer: Id128) -> Vec<Gap> {
        self.producers
            .get(&producer)
            .map(SequenceTracker::gaps)
            .unwrap_or_default()
    }

    /// Only committed positions; safe to persist.
    pub fn checkpoints(&self) -> HashMap<Id128, u64> {
        self.producers
            .iter()
            .map(|(p, t)| (*p, t.checkpoint()))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};

    fn processed(t: &mut SequenceTracker, seq: u64) {
        t.begin(seq).unwrap();
        t.complete(seq).unwrap();
    }

    #[test]
    fn out_of_order_events_are_buffered_never_auto_committed() {
        let mut t = SequenceTracker::default();
        assert_eq!(t.receive(2), Ok(Received::AfterGap { missing: 1 }));
        assert_eq!(t.receive(3), Ok(Received::AfterGap { missing: 1 }));
        assert_eq!(t.receive(1), Ok(Received::InOrder));
        processed(&mut t, 1);
        t.commit(1).unwrap();
        // 2 and 3 are buffered but not processed: the checkpoint stays at 1.
        assert_eq!(t.checkpoint(), 1);
        assert_eq!(t.commit(2), Err(CommitError::NotProcessed(2)));
        processed(&mut t, 2);
        t.commit(2).unwrap();
        assert_eq!(t.checkpoint(), 2);
    }

    #[test]
    fn double_and_invalid_commits_are_rejected() {
        let mut t = SequenceTracker::default();
        assert_eq!(t.commit(1), Err(CommitError::NotReceived(1)));
        t.receive(1).unwrap();
        assert_eq!(t.commit(1), Err(CommitError::NotProcessed(1)));
        t.begin(1).unwrap();
        assert_eq!(t.commit(1), Err(CommitError::NotProcessed(1)));
        t.complete(1).unwrap();
        t.commit(1).unwrap();
        assert_eq!(t.commit(1), Err(CommitError::AlreadyCommitted(1)));
        assert_eq!(t.receive(1), Ok(Received::Duplicate));
        assert_eq!(t.receive(0), Err(SequenceError::InvalidSequence));
        assert_eq!(t.complete(9), Err(SequenceError::NotReceived(9)));
    }

    #[test]
    fn commits_are_sequential_and_a_rejected_commit_is_retried_not_reprocessed() {
        let mut t = SequenceTracker::default();
        for seq in 1..=3 {
            t.receive(seq).unwrap();
            t.begin(seq).unwrap();
        }
        // 3 and 2 finish before 1 (concurrent processing).
        t.complete(3).unwrap();
        t.complete(2).unwrap();
        assert_eq!(
            t.commit(2),
            Err(CommitError::PredecessorPending { expected: 1 })
        );
        assert_eq!(
            t.commit(3),
            Err(CommitError::PredecessorPending { expected: 1 })
        );
        t.complete(1).unwrap();
        t.commit(1).unwrap();
        // Retry: 2 and 3 are still processed, no re-run needed.
        t.commit(2).unwrap();
        t.commit(3).unwrap();
        assert_eq!(t.checkpoint(), 3);
    }

    #[test]
    fn failure_rolls_back_only_the_failed_event() {
        let mut t = SequenceTracker::resume(10, 16);
        t.receive(11).unwrap();
        processed(&mut t, 11);
        t.commit(11).unwrap();
        t.receive(12).unwrap();
        t.begin(12).unwrap();
        t.fail(12).unwrap();
        assert_eq!(t.checkpoint(), 11);
        assert_eq!(t.commit(12), Err(CommitError::NotProcessed(12)));
        // Retry works and is not a duplicate.
        processed(&mut t, 12);
        t.commit(12).unwrap();
        assert_eq!(t.checkpoint(), 12);
    }

    #[test]
    fn a_lost_predecessor_does_not_deadlock_the_producer() {
        let mut t = SequenceTracker::default();
        t.receive(1).unwrap();
        processed(&mut t, 1);
        t.commit(1).unwrap();
        // 2 was dropped on the at-most-once bus.
        assert_eq!(t.receive(3), Ok(Received::AfterGap { missing: 1 }));
        processed(&mut t, 3);
        assert_eq!(
            t.commit(3),
            Err(CommitError::PredecessorPending { expected: 2 })
        );
        assert_eq!(t.gaps(), vec![Gap { first: 2, last: 2 }]);
        // Never skipped implicitly; the consumer decides.
        assert_eq!(t.declare_lost(3), Err(SequenceError::ReceivedNotLost(3)));
        assert_eq!(t.declare_lost(2), Ok(1));
        assert_eq!(t.lost(), 1);
        t.commit(3).unwrap();
        assert_eq!(t.checkpoint(), 3);
        // A late arrival of the lost event is a duplicate, not a new event.
        assert_eq!(t.receive(2), Ok(Received::Duplicate));
    }

    #[test]
    fn buffer_is_bounded() {
        let mut t = SequenceTracker::resume(0, 2);
        t.receive(5).unwrap();
        t.receive(6).unwrap();
        assert_eq!(t.receive(7), Err(SequenceError::BufferFull));
        assert_eq!(t.receive(5), Ok(Received::Duplicate));
    }

    #[test]
    fn resume_after_crash_redelivers_uncommitted_events() {
        let p = Id128([1; 16]);
        let mut progress = ConsumerProgress::default();
        for seq in 1..=3 {
            let at = EventPosition {
                producer: p,
                sequence: seq,
            };
            progress.receive(at).unwrap();
            progress.begin(at).unwrap();
            progress.complete(at).unwrap();
        }
        progress
            .commit(EventPosition {
                producer: p,
                sequence: 1,
            })
            .unwrap();
        // Crash after processing 2 and 3 but before committing them.
        let saved = progress.checkpoints();
        assert_eq!(saved[&p], 1);
        let mut restarted = ConsumerProgress::resume(saved, DEFAULT_MAX_PENDING);
        let at2 = EventPosition {
            producer: p,
            sequence: 2,
        };
        assert_eq!(restarted.receive(at2), Ok(Received::InOrder));
        assert_eq!(
            restarted.receive(EventPosition {
                producer: p,
                sequence: 1
            }),
            Ok(Received::Duplicate)
        );
    }

    #[test]
    fn producers_are_independent() {
        let (a, b) = (Id128([1; 16]), Id128([2; 16]));
        let mut progress = ConsumerProgress::default();
        let a1 = EventPosition {
            producer: a,
            sequence: 1,
        };
        let b5 = EventPosition {
            producer: b,
            sequence: 5,
        };
        progress.receive(a1).unwrap();
        assert_eq!(progress.receive(b5), Ok(Received::AfterGap { missing: 4 }));
        progress.begin(a1).unwrap();
        progress.complete(a1).unwrap();
        progress.commit(a1).unwrap();
        assert_eq!(progress.gaps(b), vec![Gap { first: 1, last: 4 }]);
        assert_eq!(progress.checkpoints()[&a], 1);
        assert_eq!(progress.checkpoints()[&b], 0);
    }

    #[test]
    fn concurrent_consumers_commit_every_event_exactly_once_in_order() {
        let producer = Id128([9; 16]);
        let progress = Arc::new(Mutex::new(ConsumerProgress::default()));
        const N: u64 = 400;
        {
            let mut p = progress.lock().unwrap();
            for seq in (1..=N).rev() {
                p.receive(EventPosition {
                    producer,
                    sequence: seq,
                })
                .unwrap();
            }
        }
        let committed = Arc::new(Mutex::new(Vec::new()));
        let workers: Vec<_> = (0..4)
            .map(|w| {
                let progress = Arc::clone(&progress);
                let committed = Arc::clone(&committed);
                std::thread::spawn(move || {
                    let mine: Vec<u64> = (1..=N).filter(|s| s % 4 == w).collect();
                    for &seq in &mine {
                        let at = EventPosition {
                            producer,
                            sequence: seq,
                        };
                        let mut p = progress.lock().unwrap();
                        p.begin(at).unwrap();
                        p.complete(at).unwrap();
                    }
                    let mut todo = mine;
                    while !todo.is_empty() {
                        todo.retain(|&seq| {
                            let at = EventPosition {
                                producer,
                                sequence: seq,
                            };
                            match progress.lock().unwrap().commit(at) {
                                Ok(()) => {
                                    committed.lock().unwrap().push(seq);
                                    false
                                }
                                Err(CommitError::PredecessorPending { .. }) => true,
                                Err(other) => panic!("unexpected {other:?}"),
                            }
                        });
                        std::thread::yield_now();
                    }
                })
            })
            .collect();
        for w in workers {
            w.join().unwrap();
        }
        let committed = committed.lock().unwrap();
        assert_eq!(*committed, (1..=N).collect::<Vec<_>>());
        assert_eq!(progress.lock().unwrap().checkpoints()[&producer], N);
    }
}
