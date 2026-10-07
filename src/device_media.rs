//! Optional loopback bridge for a controller's camera and microphone.
//!
//! The local helpers only use these two loopback ports. The media itself crosses
//! the already authenticated RustDesk desktop stream as DeviceMediaFrame.

use base::message_proto::DeviceMediaFrame;
use hbb_common::log;
use hbb_common::tokio::{
    self,
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpStream,
    sync::mpsc,
    task::JoinHandle,
    time::{timeout, Duration, Instant},
};
use std::io;

pub const AUDIO: u32 = 1;
pub const VIDEO: u32 = 2;
const AUDIO_BYTES: usize = 1_920; // 20 ms of 48 kHz, mono, signed 16-bit PCM
const MAX_JPEG_BYTES: usize = 256 * 1024;
const CAPTURE_ADDR: &str = "127.0.0.1:47831";
const RECEIVER_ADDR: &str = "127.0.0.1:47832";
const QUEUE_SIZE: usize = 8;

pub fn valid(frame: &DeviceMediaFrame) -> bool {
    let data = frame.data.as_ref();
    match frame.kind {
        AUDIO => data.len() == AUDIO_BYTES,
        VIDEO => {
            (4..=MAX_JPEG_BYTES).contains(&data.len())
                && data.starts_with(&[0xff, 0xd8])
                && data.ends_with(&[0xff, 0xd9])
        }
        _ => false,
    }
}

pub struct RateLimit {
    started: Instant,
    audio: u32,
    video: u32,
    bytes: usize,
}

impl RateLimit {
    pub fn new() -> Self {
        Self {
            started: Instant::now(),
            audio: 0,
            video: 0,
            bytes: 0,
        }
    }

    pub fn allow(&mut self, frame: &DeviceMediaFrame) -> bool {
        if !valid(frame) {
            return false;
        }
        if self.started.elapsed() >= Duration::from_secs(1) {
            self.started = Instant::now();
            self.audio = 0;
            self.video = 0;
            self.bytes = 0;
        }
        let size = frame.data.len();
        if self.bytes + size > 1_500_000 {
            return false;
        }
        match frame.kind {
            AUDIO if self.audio < 60 => self.audio += 1,
            VIDEO if self.video < 15 => self.video += 1,
            _ => return false,
        }
        self.bytes += size;
        true
    }
}

async fn read_frame(stream: &mut TcpStream) -> io::Result<DeviceMediaFrame> {
    let kind = stream.read_u8().await? as u32;
    let len = stream.read_u32().await? as usize;
    let max = if kind == AUDIO {
        AUDIO_BYTES
    } else {
        MAX_JPEG_BYTES
    };
    if len > max || len == 0 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "media frame too large",
        ));
    }
    let mut data = vec![0; len];
    stream.read_exact(&mut data).await?;
    let frame = DeviceMediaFrame {
        kind,
        data: data.into(),
        ..Default::default()
    };
    if !valid(&frame) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid media frame",
        ));
    }
    Ok(frame)
}

async fn write_frame(stream: &mut TcpStream, frame: &DeviceMediaFrame) -> io::Result<()> {
    if !valid(frame) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid media frame",
        ));
    }
    stream.write_u8(frame.kind as u8).await?;
    stream.write_u32(frame.data.len() as u32).await?;
    stream.write_all(frame.data.as_ref()).await
}

async fn connect_local(addr: &str) -> io::Result<TcpStream> {
    timeout(Duration::from_millis(250), async {
        let mut stream = TcpStream::connect(addr).await?;
        if stream.read_u8().await? != 1 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "media helper handshake failed",
            ));
        }
        Ok(stream)
    })
    .await
    .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "media helper unavailable"))?
}

/// Connect only after the remote desktop login succeeds. Dropping the returned
/// task closes the helper socket so capture ends with the session.
pub async fn start_capture() -> Option<(mpsc::Receiver<DeviceMediaFrame>, JoinHandle<()>)> {
    let mut stream = connect_local(CAPTURE_ADDR).await.ok()?;
    let (tx, rx) = mpsc::channel(QUEUE_SIZE);
    let task = tokio::spawn(async move {
        let mut limit = RateLimit::new();
        loop {
            match read_frame(&mut stream).await {
                Ok(frame) if limit.allow(&frame) => {
                    if tx.try_send(frame).is_err() && tx.is_closed() {
                        break;
                    }
                }
                Ok(_) => {}
                Err(err) => {
                    log::info!("Local capture helper stopped: {}", err);
                    break;
                }
            }
        }
    });
    Some((rx, task))
}

/// A helper must already be listening. One connection is opened per desktop
/// session and its bounded queue prevents a slow virtual device from blocking
/// mouse, keyboard or screen traffic.
pub async fn start_receiver() -> Option<mpsc::Sender<DeviceMediaFrame>> {
    let mut stream = connect_local(RECEIVER_ADDR).await.ok()?;
    let (tx, mut rx) = mpsc::channel::<DeviceMediaFrame>(QUEUE_SIZE);
    tokio::spawn(async move {
        while let Some(frame) = rx.recv().await {
            if let Err(err) = write_frame(&mut stream, &frame).await {
                log::info!("Local device helper stopped: {}", err);
                break;
            }
        }
    });
    Some(tx)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_wrong_frame_shape_and_excess_rate() {
        let mut limit = RateLimit::new();
        let audio = DeviceMediaFrame {
            kind: AUDIO,
            data: vec![0; AUDIO_BYTES].into(),
            ..Default::default()
        };
        assert!(!valid(&DeviceMediaFrame {
            kind: 9,
            ..audio.clone()
        }));
        assert!(!valid(&DeviceMediaFrame {
            data: vec![0; AUDIO_BYTES - 1].into(),
            ..audio.clone()
        }));
        for _ in 0..60 {
            assert!(limit.allow(&audio));
        }
        assert!(!limit.allow(&audio));
    }
}
