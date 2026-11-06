//! Subscriber queues and drop policies (Phase 0 §4).
//!
//! The Event Bus is at-most-once and never blocks a publisher:
//!
//! * Every subscriber has its own bounded queue.
//! * A full queue drops according to its [`DropPolicy`]; the drop is counted.
//! * [`Fanout::publish`] never waits for a subscriber. If a subscriber's queue
//!   is busy (locked by a slow consumer), the event is dropped *for that
//!   subscriber only* and counted as such.
//! * Drops are why sequence gaps are normal on the bus. Durable delivery and
//!   replay belong to the Event Store (Phase 2), not here.

use super::envelope::{EventEnvelope, UnixTimestampNs};
use std::collections::VecDeque;
use std::sync::{Arc, Mutex, TryLockError};

pub trait Timestamped {
    fn timestamp_ns(&self) -> UnixTimestampNs;
}

impl Timestamped for EventEnvelope {
    fn timestamp_ns(&self) -> UnixTimestampNs {
        self.timestamp
    }
}

impl<T: Timestamped> Timestamped for Arc<T> {
    fn timestamp_ns(&self) -> UnixTimestampNs {
        (**self).timestamp_ns()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DropPolicy {
    /// Full queue: drop the oldest queued event, enqueue the new one.
    DropOldest,
    /// Full queue: reject the new event.
    DropNewest,
    /// Drop events older than `max_age_ns` (also a new one that is already
    /// too old). If the queue is still full after that, reject the new event.
    DropByAge { max_age_ns: i64 },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PushOutcome {
    Enqueued,
    /// Enqueued after dropping this many older events.
    EnqueuedAfterDropping(usize),
    Rejected,
}

#[derive(Debug)]
pub struct SubscriberQueue<T> {
    items: VecDeque<T>,
    capacity: usize,
    policy: DropPolicy,
    dropped: u64,
}

impl<T: Timestamped> SubscriberQueue<T> {
    pub fn new(capacity: usize, policy: DropPolicy) -> Self {
        assert!(capacity > 0, "a subscriber queue needs room for one event");
        Self {
            items: VecDeque::with_capacity(capacity),
            capacity,
            policy,
            dropped: 0,
        }
    }

    pub fn len(&self) -> usize {
        self.items.len()
    }

    pub fn is_empty(&self) -> bool {
        self.items.is_empty()
    }

    /// Events dropped from this queue so far.
    pub fn dropped(&self) -> u64 {
        self.dropped
    }

    pub fn pop(&mut self) -> Option<T> {
        self.items.pop_front()
    }

    fn expire(&mut self, now: UnixTimestampNs, max_age_ns: i64) -> usize {
        let cutoff = now.0.saturating_sub(max_age_ns);
        let before = self.items.len();
        self.items.retain(|e| e.timestamp_ns().0 >= cutoff);
        before - self.items.len()
    }

    /// Never blocks; O(1) except for expiry under `DropByAge`.
    pub fn push(&mut self, event: T, now: UnixTimestampNs) -> PushOutcome {
        let outcome = match self.policy {
            DropPolicy::DropOldest => {
                if self.items.len() < self.capacity {
                    self.items.push_back(event);
                    PushOutcome::Enqueued
                } else {
                    self.items.pop_front();
                    self.items.push_back(event);
                    PushOutcome::EnqueuedAfterDropping(1)
                }
            }
            DropPolicy::DropNewest => {
                if self.items.len() < self.capacity {
                    self.items.push_back(event);
                    PushOutcome::Enqueued
                } else {
                    PushOutcome::Rejected
                }
            }
            DropPolicy::DropByAge { max_age_ns } => {
                let expired = self.expire(now, max_age_ns);
                if event.timestamp_ns().0 < now.0.saturating_sub(max_age_ns)
                    || self.items.len() >= self.capacity
                {
                    self.dropped += expired as u64;
                    self.dropped += 1;
                    return PushOutcome::Rejected;
                }
                self.items.push_back(event);
                if expired == 0 {
                    PushOutcome::Enqueued
                } else {
                    PushOutcome::EnqueuedAfterDropping(expired)
                }
            }
        };
        match outcome {
            PushOutcome::Enqueued => {}
            PushOutcome::EnqueuedAfterDropping(n) => self.dropped += n as u64,
            PushOutcome::Rejected => self.dropped += 1,
        }
        outcome
    }
}

/// Per-subscriber result of one publish.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Delivery {
    Queued(PushOutcome),
    /// The subscriber's queue was busy; dropped for this subscriber.
    DroppedBusy,
}

/// Broadcast to independent subscriber queues without ever waiting.
#[derive(Debug)]
pub struct Fanout<T> {
    subscribers: Vec<Arc<Mutex<SubscriberQueue<T>>>>,
    busy_drops: u64,
}

impl<T: Timestamped + Clone> Default for Fanout<T> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T: Timestamped + Clone> Fanout<T> {
    pub fn new() -> Self {
        Self {
            subscribers: Vec::new(),
            busy_drops: 0,
        }
    }

    pub fn subscribe(
        &mut self,
        capacity: usize,
        policy: DropPolicy,
    ) -> Arc<Mutex<SubscriberQueue<T>>> {
        let queue = Arc::new(Mutex::new(SubscriberQueue::new(capacity, policy)));
        self.subscribers.push(Arc::clone(&queue));
        queue
    }

    pub fn busy_drops(&self) -> u64 {
        self.busy_drops
    }

    pub fn publish(&mut self, event: &T, now: UnixTimestampNs) -> Vec<Delivery> {
        let mut report = Vec::with_capacity(self.subscribers.len());
        for queue in &self.subscribers {
            let delivery = match queue.try_lock() {
                Ok(mut q) => Delivery::Queued(q.push(event.clone(), now)),
                // A poisoned queue belongs to a crashed subscriber: drop, never panic.
                Err(TryLockError::WouldBlock) | Err(TryLockError::Poisoned(_)) => {
                    self.busy_drops += 1;
                    Delivery::DroppedBusy
                }
            };
            report.push(delivery);
        }
        report
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc;
    use std::time::{Duration, Instant};

    #[derive(Debug, Clone, PartialEq)]
    struct Ev(u64, i64);

    impl Timestamped for Ev {
        fn timestamp_ns(&self) -> UnixTimestampNs {
            UnixTimestampNs(self.1)
        }
    }

    const NOW: UnixTimestampNs = UnixTimestampNs(1_000);

    fn drain(q: &mut SubscriberQueue<Ev>) -> Vec<u64> {
        std::iter::from_fn(|| q.pop()).map(|e| e.0).collect()
    }

    #[test]
    fn drop_oldest() {
        let mut q = SubscriberQueue::new(2, DropPolicy::DropOldest);
        assert_eq!(q.push(Ev(1, 1000), NOW), PushOutcome::Enqueued);
        assert_eq!(q.push(Ev(2, 1000), NOW), PushOutcome::Enqueued);
        assert_eq!(
            q.push(Ev(3, 1000), NOW),
            PushOutcome::EnqueuedAfterDropping(1)
        );
        assert_eq!(q.dropped(), 1);
        assert_eq!(drain(&mut q), vec![2, 3]);
    }

    #[test]
    fn drop_newest() {
        let mut q = SubscriberQueue::new(2, DropPolicy::DropNewest);
        q.push(Ev(1, 1000), NOW);
        q.push(Ev(2, 1000), NOW);
        assert_eq!(q.push(Ev(3, 1000), NOW), PushOutcome::Rejected);
        assert_eq!(q.dropped(), 1);
        assert_eq!(drain(&mut q), vec![1, 2]);
    }

    #[test]
    fn drop_by_age() {
        let mut q = SubscriberQueue::new(2, DropPolicy::DropByAge { max_age_ns: 100 });
        q.push(Ev(1, 850), UnixTimestampNs(900));
        q.push(Ev(2, 950), UnixTimestampNs(950));
        // At t=1000, event 1 (850) is older than 100ns and expires.
        assert_eq!(
            q.push(Ev(3, 1000), NOW),
            PushOutcome::EnqueuedAfterDropping(1)
        );
        // Full of fresh events: the new one is rejected.
        assert_eq!(q.push(Ev(4, 1000), NOW), PushOutcome::Rejected);
        // A new event that is already too old is rejected.
        let mut q2 = SubscriberQueue::new(2, DropPolicy::DropByAge { max_age_ns: 100 });
        assert_eq!(q2.push(Ev(9, 10), NOW), PushOutcome::Rejected);
        assert_eq!(q.dropped(), 2);
        assert_eq!(drain(&mut q), vec![2, 3]);
    }

    #[test]
    fn a_slow_subscriber_never_blocks_the_publisher() {
        let mut bus: Fanout<Ev> = Fanout::new();
        let fast = bus.subscribe(100_000, DropPolicy::DropOldest);
        let slow = bus.subscribe(1, DropPolicy::DropNewest);
        let stuck = bus.subscribe(10, DropPolicy::DropOldest);

        // A subscriber that grabs its queue and never lets go.
        let (locked_tx, locked_rx) = mpsc::channel();
        let (release_tx, release_rx) = mpsc::channel::<()>();
        let holder = {
            let stuck = Arc::clone(&stuck);
            std::thread::spawn(move || {
                let _guard = stuck.lock().unwrap();
                locked_tx.send(()).unwrap();
                release_rx.recv().unwrap();
            })
        };
        locked_rx.recv().unwrap();

        let started = Instant::now();
        for i in 0..10_000 {
            let report = bus.publish(&Ev(i, 1000), NOW);
            assert_eq!(report[2], Delivery::DroppedBusy);
        }
        assert!(started.elapsed() < Duration::from_secs(5));
        release_tx.send(()).unwrap();
        holder.join().unwrap();

        assert_eq!(fast.lock().unwrap().len(), 10_000);
        let slow = slow.lock().unwrap();
        assert_eq!(slow.len(), 1);
        assert_eq!(slow.dropped(), 9_999);
        assert_eq!(bus.busy_drops(), 10_000);
        assert!(stuck.lock().unwrap().is_empty());
    }

    #[test]
    fn a_crashed_subscriber_does_not_break_the_bus() {
        let mut bus: Fanout<Ev> = Fanout::new();
        let crashed = bus.subscribe(4, DropPolicy::DropOldest);
        let healthy = bus.subscribe(4, DropPolicy::DropOldest);
        let _ = std::thread::spawn(move || {
            let _guard = crashed.lock().unwrap();
            panic!("subscriber crashed while holding its queue");
        })
        .join();
        let report = bus.publish(&Ev(1, 1000), NOW);
        assert_eq!(report[0], Delivery::DroppedBusy);
        assert_eq!(report[1], Delivery::Queued(PushOutcome::Enqueued));
        assert_eq!(healthy.lock().unwrap().len(), 1);
    }
}
