$conn = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
  Stop-Process -Id $conn.OwningProcess -Force
  Start-Sleep -Seconds 2
}
Set-Location 'C:\Users\31560\Documents\00_open\legged_studio'
Start-Process -FilePath '.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','backend.api_complete:app','--host','127.0.0.1','--port','8765' -WindowStyle Hidden -RedirectStandardOutput 'C:\Users\31560\AppData\Local\Temp\ls_server.log' -RedirectStandardError 'C:\Users\31560\AppData\Local\Temp\ls_server.err'
Start-Sleep -Seconds 8
Write-Output "restarted"
