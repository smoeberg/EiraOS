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

    pub fn push(&mut self, bytes: &[u8]) {
        if !self.poisoned {
            self.buf.extend_from_slice(bytes);
        }
    }

    /// Next complete frame, `Ok(None)` if more bytes are needed.
    pub fn next_frame(&mut self) -> Result<Option<Vec<u8>>, FrameError> {
        if self.poisoned {
            return Err(FrameError::Poisoned);
        }
        if self.buf.len() < 4 {
            return Ok(None);
        }
        let len = u32::from_be_bytes(self.buf[..4].try_into().unwrap()) as usize;
        if len == 0 || len > self.max {
            self.poisoned = true;
            self.buf = Vec::new();
            return Err(if len == 0 {
                FrameError::Empty
            } else {
                FrameError::TooLarge { len, max: self.max }
            });
        }
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

        // Two frames in one push.
        let mut dec = FrameDecoder::default();
        dec.push(&stream);
        assert_eq!(dec.next_frame().unwrap().unwrap(), b"\xa0");
        assert_eq!(dec.next_frame().unwrap().unwrap(), b"\x82\x01\x02");
        assert_eq!(dec.next_frame().unwrap(), None);

        // One byte at a time.
        let mut dec = FrameDecoder::default();
        let mut got = Vec::new();
        for byte in &stream {
            dec.push(std::slice::from_ref(byte));
            while let Some(frame) = dec.next_frame().unwrap() {
                got.push(frame);
            }
        }
        assert_eq!(got, vec![b"\xa0".to_vec(), b"\x82\x01\x02".to_vec()]);

        // Half a header, then the rest.
        let mut dec = FrameDecoder::default();
        dec.push(&b[..2]);
        assert_eq!(dec.next_frame().unwrap(), None);
        dec.push(&b[2..5]);
        assert_eq!(dec.next_frame().unwrap(), None);
        dec.push(&b[5..]);
        assert_eq!(dec.next_frame().unwrap().unwrap(), b"\x82\x01\x02");
        assert_eq!(dec.buffered(), 0);
    }

    #[test]
    fn oversized_and_empty_frames_poison_the_stream() {
        let mut dec = FrameDecoder::new(8);
        dec.push(&9u32.to_be_bytes());
        assert_eq!(
            dec.next_frame(),
            Err(FrameError::TooLarge { len: 9, max: 8 })
        );
        dec.push(&encode_frame(b"\xa0").unwrap());
        assert_eq!(dec.next_frame(), Err(FrameError::Poisoned));

        let mut dec = FrameDecoder::default();
        dec.push(&0u32.to_be_bytes());
        assert_eq!(dec.next_frame(), Err(FrameError::Empty));

        // The limit is enforced from the header alone, before buffering.
        let mut dec = FrameDecoder::default();
        dec.push(&u32::MAX.to_be_bytes());
        assert!(matches!(dec.next_frame(), Err(FrameError::TooLarge { .. })));
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
