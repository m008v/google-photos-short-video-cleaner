$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExecutable = Join-Path $scriptDirectory ".venv\Scripts\python.exe"
$cleanerScript = Join-Path $scriptDirectory "gphotos_short_video_cleaner.py"
$debugAddress = "127.0.0.1:9222"
$debugUrl = "http://$debugAddress/json/version"
$profileDirectory = Join-Path $env:USERPROFILE ".gphotos-short-video-cleaner\chrome-login-profile"

function Test-DebugEndpoint {
    try {
        $response = Invoke-RestMethod -Uri $debugUrl -TimeoutSec 2
        return [bool]$response.webSocketDebuggerUrl
    }
    catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    Write-Host "Chưa cài đặt. Hãy chạy setup_windows.bat trước." -ForegroundColor Red
    exit 1
}

$chromeCandidates = @(
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe")
    (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe")
    (Join-Path $env:LocalAppData "Google\Chrome\Application\chrome.exe")
)
$chromeExecutable = $chromeCandidates |
    Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
    Select-Object -First 1

if (-not $chromeExecutable) {
    Write-Host "Không tìm thấy Google Chrome. Hãy cài hoặc cập nhật Chrome rồi chạy lại." -ForegroundColor Red
    exit 1
}

if ($args -contains "--launcher-self-test") {
    Write-Host "Kiểm tra launcher thành công: Python và Chrome đều sẵn sàng." -ForegroundColor Green
    exit 0
}

if (-not (Test-DebugEndpoint)) {
    Write-Host "Đang mở Chrome thường để Google cho phép đăng nhập..."
    $chromeArguments = @(
        "--remote-debugging-address=127.0.0.1"
        "--remote-debugging-port=9222"
        "--user-data-dir=`"$profileDirectory`""
        "--lang=vi-VN"
        "--disable-background-timer-throttling"
        "--disable-backgrounding-occluded-windows"
        "--disable-renderer-backgrounding"
        "https://photos.google.com/"
    )
    Start-Process -FilePath $chromeExecutable -ArgumentList $chromeArguments
}
else {
    Write-Host "Đã tìm thấy Chrome dành riêng cho tool tại $debugAddress."
}

Write-Host ""
Write-Host "Đăng nhập Google hoàn toàn trong cửa sổ Chrome vừa mở."
Write-Host "Chỉ tiếp tục khi trang Google Photos đã hiển thị bình thường."
Write-Host "Không đóng Chrome trong lúc tool đang chạy."
Write-Host "Khi tool hoàn tất, hãy đóng cửa sổ Chrome này để tắt cổng debug."
[void](Read-Host "Nhấn Enter để Selenium gắn vào Chrome")

if (-not (Test-DebugEndpoint)) {
    Write-Host "Không kết nối được Chrome tại $debugAddress. Hãy giữ cửa sổ Chrome mở rồi chạy lại." -ForegroundColor Red
    exit 1
}

& $pythonExecutable $cleanerScript --debugger-address $debugAddress --language vi-VN --close-browser @args
exit $LASTEXITCODE
