//! Pi-side TCP streamer + goal receiver.
//!
//! Two independent listeners:
//!
//! * [`Telemetry`] (default port 9874) — server pushes pose + map +
//!   path + scan to whichever single client is connected. Drops on
//!   client disconnect; ready for the next one.
//! * [`GoalServer`] (default port 9875) — server reads goals from a
//!   single connected client and forwards them via an mpsc channel.
//!
//! Why two ports? Telemetry is high-rate firehose, goals are sparse
//! click events; muxing them on one socket means you lose the ability
//! to drop telemetry on slow consumers without also losing goals.
//!
//! Both listeners are non-blocking and don't spawn threads — call
//! `tick()` from the runtime's main loop to accept connections and
//! drain inbound goals. Network errors deliberately fall through as
//! "client gone" rather than killing the runtime.

use std::io::{self, ErrorKind, Read};
use std::net::{TcpListener, TcpStream};
use std::time::Duration;

use crate::wire::{
    self, Goal, Hello, Message, Path, Pose, Scan, MAX_FRAME_LEN,
    PROTOCOL_VERSION,
};

const TELEMETRY_DEFAULT_PORT: u16 = 9874;
const GOAL_DEFAULT_PORT:      u16 = 9875;

pub struct Telemetry {
    listener: TcpListener,
    client:   Option<TcpStream>,
}

impl Telemetry {
    pub fn bind(port: u16) -> io::Result<Self> {
        let listener = TcpListener::bind(("0.0.0.0", port))?;
        listener.set_nonblocking(true)?;
        Ok(Self { listener, client: None })
    }

    pub fn bind_default() -> io::Result<Self> {
        Self::bind(TELEMETRY_DEFAULT_PORT)
    }

    /// Accept a pending connection if any. No-op when a client is
    /// already connected — single-consumer model.
    pub fn poll_accept(&mut self) {
        if self.client.is_some() { return; }
        match self.listener.accept() {
            Ok((mut s, addr)) => {
                let _ = s.set_nodelay(true);
                let _ = s.set_nonblocking(false);
                // Bounded blocking: a viewer that vanishes without RST
                // (laptop sleep, Wi-Fi drop) leaves the TCP send buffer
                // full; without a timeout the next send would block the
                // maploc worker for the TCP retransmission timeout —
                // minutes — while the duck keeps walking on its last
                // stale command. On timeout we drop the client instead.
                let _ = s.set_write_timeout(Some(Duration::from_millis(500)));
                if wire::write_hello(&mut s, Hello { version: PROTOCOL_VERSION }).is_ok() {
                    eprintln!("[maploc] telemetry client connected from {addr}");
                    self.client = Some(s);
                }
            }
            Err(e) if e.kind() == ErrorKind::WouldBlock => {}
            Err(e) => eprintln!("[maploc] telemetry accept error: {e}"),
        }
    }

    pub fn has_client(&self) -> bool { self.client.is_some() }

    fn send<F>(&mut self, write: F)
    where F: FnOnce(&mut TcpStream) -> io::Result<()> {
        if let Some(s) = self.client.as_mut() {
            if let Err(e) = write(s) {
                eprintln!("[maploc] telemetry client dropped: {e}");
                self.client = None;
            }
        }
    }

    pub fn send_pose(&mut self, p: Pose)         { self.send(|s| wire::write_pose(s, p)); }
    pub fn send_map(&mut self, bytes: &[u8])      { self.send(|s| wire::write_map(s, bytes)); }
    pub fn send_path(&mut self, p: &Path)         { self.send(|s| wire::write_path(s, p)); }
    pub fn send_scan(&mut self, sc: &Scan)        { self.send(|s| wire::write_scan(s, sc)); }
}

pub struct GoalServer {
    listener: TcpListener,
    client:   Option<TcpStream>,
    /// Per-client reassembly buffer. `read_exact` on a non-blocking
    /// socket CONSUMES partial bytes before returning `WouldBlock` (std
    /// documents the count as unspecified), so parsing straight off the
    /// socket desynchronizes the frame stream whenever a frame arrives
    /// split across TCP segments. All bytes land here first; complete
    /// frames are parsed out of the front.
    buf: Vec<u8>,
}

impl GoalServer {
    pub fn bind(port: u16) -> io::Result<Self> {
        let listener = TcpListener::bind(("0.0.0.0", port))?;
        listener.set_nonblocking(true)?;
        Ok(Self { listener, client: None, buf: Vec::new() })
    }

    pub fn bind_default() -> io::Result<Self> {
        Self::bind(GOAL_DEFAULT_PORT)
    }

    /// Drain accepted connections + ALL inbound bytes. Returns the
    /// most-recent complete goal received (older goals are discarded —
    /// the user just clicked again, the new click wins). The old code
    /// read at most one message per tick, so N rapid clicks were
    /// delivered oldest-first over N ticks, each triggering a replan to
    /// a stale goal.
    pub fn tick(&mut self) -> Option<Goal> {
        // Accept.
        if self.client.is_none() {
            match self.listener.accept() {
                Ok((s, addr)) => {
                    let _ = s.set_nonblocking(true);
                    eprintln!("[maploc] goal client connected from {addr}");
                    self.client = Some(s);
                    self.buf.clear();
                }
                Err(e) if e.kind() == ErrorKind::WouldBlock => {}
                Err(e) => eprintln!("[maploc] goal accept error: {e}"),
            }
        }
        // Pull everything available off the socket into the buffer.
        let mut drop_client = false;
        if let Some(s) = self.client.as_mut() {
            let mut chunk = [0u8; 1024];
            loop {
                match s.read(&mut chunk) {
                    Ok(0) => { // orderly close
                        eprintln!("[maploc] goal client disconnected");
                        drop_client = true;
                        break;
                    }
                    Ok(n) => {
                        self.buf.extend_from_slice(&chunk[..n]);
                        if self.buf.len() > MAX_FRAME_LEN + 8 {
                            eprintln!("[maploc] goal client flooding — dropped");
                            drop_client = true;
                            break;
                        }
                    }
                    Err(e) if e.kind() == ErrorKind::WouldBlock => break,
                    Err(e) => {
                        eprintln!("[maploc] goal client dropped: {e}");
                        drop_client = true;
                        break;
                    }
                }
            }
        }
        // Parse every complete frame out of the buffer; newest goal wins.
        let mut latest = None;
        if self.client.is_some() {
            loop {
                if self.buf.len() < 4 { break; }
                let len_field = u32::from_le_bytes(self.buf[..4].try_into().unwrap());
                let len = len_field as usize;
                if len < 1 || len > MAX_FRAME_LEN {
                    eprintln!("[maploc] goal client sent bad frame length {len_field} — dropped");
                    drop_client = true;
                    break;
                }
                let total = 4 + len;
                if self.buf.len() < total { break; } // frame incomplete — wait
                match wire::read_message(&mut &self.buf[..total]) {
                    Ok(Message::Goal(g)) => { latest = Some(g); }
                    Ok(_other)           => { /* ignore; we only accept goals */ }
                    Err(e) => {
                        eprintln!("[maploc] goal client sent bad frame ({e}) — dropped");
                        drop_client = true;
                    }
                }
                self.buf.drain(..total);
                if drop_client { break; }
            }
        }
        if drop_client {
            self.client = None;
            self.buf.clear();
        }
        latest
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpStream;
    use std::time::{Duration, Instant};

    #[test]
    fn telemetry_handshake_and_pose() {
        let mut srv = Telemetry::bind(0).unwrap();
        let port = srv.listener.local_addr().unwrap().port();
        let _client = std::thread::spawn(move || {
            let mut s = TcpStream::connect(("127.0.0.1", port)).unwrap();
            // Read the Hello frame.
            let mut buf = [0u8; 9];   // 4 len + 1 tag + 4 version
            s.read_exact(&mut buf).unwrap();
            assert_eq!(buf[4], crate::wire::TAG_HELLO);
        });

        let deadline = Instant::now() + Duration::from_secs(2);
        while !srv.has_client() && Instant::now() < deadline {
            srv.poll_accept();
            std::thread::sleep(Duration::from_millis(10));
        }
        assert!(srv.has_client(), "expected telemetry client to connect");
    }

    #[test]
    fn goal_server_receives_click() {
        let mut srv = GoalServer::bind(0).unwrap();
        let port = srv.listener.local_addr().unwrap().port();
        let mut s = TcpStream::connect(("127.0.0.1", port)).unwrap();
        crate::wire::write_goal(&mut s, Goal { x: 0.5, y: -1.2 }).unwrap();
        s.flush().unwrap();
        // Spin tick() until the goal arrives.
        let deadline = Instant::now() + Duration::from_secs(2);
        let mut got = None;
        while Instant::now() < deadline && got.is_none() {
            got = srv.tick();
            std::thread::sleep(Duration::from_millis(10));
        }
        let g = got.expect("expected a goal to arrive");
        assert_eq!(g.x, 0.5);
        assert_eq!(g.y, -1.2);
    }
}
