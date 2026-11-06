//! Stream framing: `u32 big-endian length || canonical CBOR message`.
//!
//! The decoder is incremental: it accepts bytes in arbitrary chunks (half
//! frames, several frames at once, one byte at a time). A length of zero or
//! above the limit is a protocol violation; the connection must be closed.

pub const MAX_FRAME_LEN: usize = 16 * 1024 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FrameError {
    Empty,
    TooLarge {
        len: usize,
        max: usize,
    },
    /// A previous error poisoned the stream; it cannot be resynchronised.
    Poisoned,
}

pub fn encode_frame(message: &[u8]) -> Result<Vec<u8>, FrameError> {
    if message.is_empty() {
        return Err(FrameError::Empty);
    }
    if message.len() > MAX_FRAME_LEN {
        return Err(FrameError::TooLarge {
            len: message.len(),
            max: MAX_FRAME_LEN,
        });
    }
    let mut out = Vec::with_capacity(4 + message.len());
    out.extend_from_slice(&(message.len() as u32).to_be_bytes());
    out.extend_from_slice(message);
    Ok(out)
}

#[derive(Debug)]
pub struct FrameDecoder {
    buf: Vec<u8>,
    max: usize,
    poisoned: bool,
}

impl Default for FrameDecoder {
    fn default() -> Self {
        Self::new(MAX_FRAME_LEN)
    }
}

impl FrameDecoder {
    pub fn new(max: usize) -> Self {
        Self {
            buf: Vec::new(),
            max: max.min(MAX_FRAME_LEN),
            poisoned: false,
        }
    }

    /// Most bytes the decoder ever holds: one header plus one maximal frame.
    pub fn capacity(&self) -> usize {
        4 + self.max
    }

    /// Offer bytes from the stream. Returns how many were accepted; the
    /// caller drains frames with [`next_frame`](Self::next_frame) and offers
    /// the rest again. Memory is bounded by [`capacity`](Self::capacity),
    /// and an oversized or empty length header is rejected here, as soon as
    /// its four bytes have arrived — before any payload is buffered.
    pub fn push(&mut self, bytes: &[u8]) -> Result<usize, FrameError> {
        if self.poisoned {
            return Err(FrameError::Poisoned);
        }
        let room = self.capacity() - self.buf.len();
        let take = bytes.len().min(room);
        self.buf.extend_from_slice(&bytes[..take]);
        if let Some(error) = self.header_error() {
            return Err(error);
        }
        Ok(take)
    }

    /// Convenience: feed a whole chunk, draining frames as they complete.
    /// Memory stays bounded by `capacity()` however large `bytes` is.
    pub fn push_all(&mut self, mut bytes: &[u8]) -> Result<Vec<Vec<u8>>, FrameError> {
        let mut frames = Vec::new();
        loop {
            let taken = self.push(bytes)?;
            bytes = &bytes[taken..];
            while let Some(frame) = self.next_frame()? {
                frames.push(frame);
            }
            if bytes.is_empty() {
                return Ok(frames);
            }
            if taken == 0 {
                // Full buffer and no complete frame: cannot happen while the
                // header check holds, but never spin.
                return Err(FrameError::Poisoned);
            }
        }
    }

    fn header_error(&mut self) -> Option<FrameError> {
        if self.buf.len() < 4 {
            return None;
        }
        let len = u32::from_be_bytes(self.buf[..4].try_into().unwrap()) as usize;
        if len != 0 && len <= self.max {
            return None;
        }
        self.poisoned = true;
        self.buf = Vec::new();
        Some(if len == 0 {
            FrameError::Empty
        } else {
            FrameError::TooLarge { len, max: self.max }
        })
    }

    /// Next complete frame, `Ok(None)` if more bytes are needed.
    pub fn next_frame(&mut self) -> Result<Option<Vec<u8>>, FrameError> {
        if self.poisoned {
            return Err(FrameError::Poisoned);
        }
        if let Some(error) = self.header_error() {
            return Err(error);
        }
        if self.buf.len() < 4 {
            return Ok(None);
        }
        let len = u32::from_be_bytes(self.buf[..4].try_into().unwrap()) as usize;
        if self.buf.len() < 4 + len {
            return Ok(None);
        }
        let frame = self.buf[4..4 + len].to_vec();
        self.buf.drain(..4 + len);
        Ok(Some(frame))
    }

    /// Bytes received but not yet part of a complete frame.
    pub fn buffered(&self) -> usize {
        self.buf.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn partial_concatenated_and_byte_by_byte() {
        let a = encode_frame(b"\xa0").unwrap();
        let b = encode_frame(b"\x82\x01\x02").unwrap();
        let stream: Vec<u8> = [a.clone(), b.clone()].concat();

        // Two frames in one chunk.
        let mut dec = FrameDecoder::default();
        assert_eq!(
            dec.push_all(&stream).unwrap(),
            vec![b"\xa0".to_vec(), b"\x82\x01\x02".to_vec()]
        );

        // One byte at a time.
        let mut dec = FrameDecoder::default();
        let mut got = Vec::new();
        for byte in &stream {
            assert_eq!(dec.push(std::slice::from_ref(byte)).unwrap(), 1);
            while let Some(frame) = dec.next_frame().unwrap() {
                got.push(frame);
            }
        }
        assert_eq!(got, vec![b"\xa0".to_vec(), b"\x82\x01\x02".to_vec()]);

        // Half a header, then the rest.
        let mut dec = FrameDecoder::default();
        dec.push(&b[..2]).unwrap();
        assert_eq!(dec.next_frame().unwrap(), None);
        dec.push(&b[2..5]).unwrap();
        assert_eq!(dec.next_frame().unwrap(), None);
        dec.push(&b[5..]).unwrap();
        assert_eq!(dec.next_frame().unwrap().unwrap(), b"\x82\x01\x02");
        assert_eq!(dec.buffered(), 0);
    }

    #[test]
    fn oversized_and_empty_headers_are_rejected_in_push() {
        let mut dec = FrameDecoder::new(8);
        assert_eq!(
            dec.push(&9u32.to_be_bytes()),
            Err(FrameError::TooLarge { len: 9, max: 8 })
        );
        assert_eq!(
            dec.push(&encode_frame(b"\xa0").unwrap()),
            Err(FrameError::Poisoned)
        );
        assert_eq!(dec.next_frame(), Err(FrameError::Poisoned));

        let mut dec = FrameDecoder::default();
        assert_eq!(dec.push(&0u32.to_be_bytes()), Err(FrameError::Empty));

        let mut dec = FrameDecoder::default();
        assert!(matches!(
            dec.push(&u32::MAX.to_be_bytes()),
            Err(FrameError::TooLarge { .. })
        ));
    }

    /// Regression (review of #134): an oversized header followed by payload
    /// in the same chunk must be refused without buffering the payload.
    #[test]
    fn an_oversized_frame_is_refused_before_its_payload_is_buffered() {
        let mut dec = FrameDecoder::new(1024);
        let mut chunk = (1_000_000u32).to_be_bytes().to_vec();
        chunk.extend(vec![0u8; 64 * 1024]);
        assert!(matches!(dec.push(&chunk), Err(FrameError::TooLarge { .. })));
        assert_eq!(dec.buffered(), 0);
    }

    /// Regression (review of #134): push never holds more than one header
    /// plus one maximal frame, however much a peer sends at once.
    #[test]
    fn buffered_bytes_are_bounded_by_capacity() {
        let mut dec = FrameDecoder::new(16);
        let frame = encode_frame(&[0xa0; 16]).unwrap();
        let flood: Vec<u8> = frame
            .iter()
            .copied()
            .cycle()
            .take(20 * frame.len())
            .collect();
        // A single push accepts at most `capacity()` bytes.
        assert_eq!(dec.push(&flood).unwrap(), dec.capacity());
        assert!(dec.buffered() <= dec.capacity());
        // push_all drains as it goes and still never exceeds capacity.
        let mut dec = FrameDecoder::new(16);
        assert_eq!(dec.push_all(&flood).unwrap().len(), 20);
        assert_eq!(dec.buffered(), 0);
    }

    #[test]
    fn encoder_enforces_the_same_limits() {
        assert_eq!(encode_frame(b""), Err(FrameError::Empty));
        assert!(matches!(
            encode_frame(&vec![0; MAX_FRAME_LEN + 1]),
            Err(FrameError::TooLarge { .. })
        ));
    }
}
