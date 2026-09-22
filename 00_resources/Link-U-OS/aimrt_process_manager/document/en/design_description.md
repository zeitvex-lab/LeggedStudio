## Main design

aimrt_process_manager uses the overall framework of `AIMRT` to load and initialize the necessary plugins. If you are familiar with `AIMRT`, 
you will find that the current repository borrows a portion of `AIMRT`'s initialization code in main.cc. On top of this framework, the following
functionalities are implemented:
- HTTP server based on the framework
- Process management
- Process startup
- Multi-process log persistence
- Persistent storage of process state

## start process

When creating a process, a two-stage fork approach is used to achieve complete isolation from the current process. The first fork creates an
intermediate process primarily used for communication with the main process. The second fork then sets environment variables, as well as attributes
such as I/O, gid, uid, and session_id, and finally performs the exec operation.

## stop process


Stopping a running process involves two steps:
- First, `kill -15 -pid` sends a negative PID, indicating that a 15 signal is sent to all processes within the session.
- If the child process does not completely exit within the timeout period, a -9 signal is sent to every process in the entire process group.