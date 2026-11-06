# Serve NeoKeys with the FP10 Lights bridge on http://localhost (a secure context, so Chrome allows Web MIDI).
# NeoKeys' index.html is served with fp10-bridge.js added and its Cloudflare analytics beacon removed; the
# file on disk is never changed. Duel (duel/) is served as it is, on /duel/. Works in Windows PowerShell 5.1
# and PowerShell 7, nothing to install.
#
#   powershell -ExecutionPolicy Bypass -File serve.ps1 [-Port 8765] [-NoBrowser] [-Open duel/]
param(
    [int]$Port = 8765,
    [switch]$NoBrowser,
    [string]$Open = ''      # the page to open: '' for NeoKeys, 'duel/' for Duel
)
$ErrorActionPreference = 'Stop'

$here = $PSScriptRoot
$neokeys = Join-Path $here 'neokeys'
if (-not (Test-Path (Join-Path $neokeys 'index.html'))) {
    if ($Open -eq '') { Write-Error "NeoKeys is missing from $neokeys. Run: git submodule update --init" }
    Write-Warning "NeoKeys is missing from $neokeys (git submodule update --init); serving Duel only."
}

$types = @{
    '.html' = 'text/html; charset=utf-8'; '.js' = 'text/javascript; charset=utf-8'
    '.css' = 'text/css; charset=utf-8'; '.json' = 'application/json'; '.png' = 'image/png'
    '.jpg' = 'image/jpeg'; '.svg' = 'image/svg+xml'; '.ico' = 'image/x-icon'; '.mid' = 'audio/midi'
}

function Get-Page {
    $html = [IO.File]::ReadAllText((Join-Path $neokeys 'index.html'), [Text.Encoding]::UTF8)
    $html = [regex]::Replace($html, '<script[^>]*cloudflareinsights[^>]*>\s*</script>\s*', '')
    $tag = '<script src="/fp10-bridge.js"></script>'
    $at = $html.LastIndexOf('</body>')
    if ($at -lt 0) { return $html + $tag }
    return $html.Insert($at, $tag + "`n")
}

$listener = New-Object Net.HttpListener
$url = "http://localhost:$Port/"
$listener.Prefixes.Add($url)
$listener.Start()
Write-Host "NeoKeys + FP10 Lights on $url, Duel on ${url}duel/ (Ctrl+C to stop)"
if (-not $NoBrowser) { Start-Process ($url + $Open) }

try {
    while ($listener.IsListening) {
        $pending = $listener.GetContextAsync()
        while (-not $pending.Wait(500)) { }   # lets Ctrl+C through
        $ctx = $pending.Result
        $path = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath)
        $res = $ctx.Response
        try {
            if ($path -eq '/duel') {
                # Duel's scripts are relative to /duel/
                $res.StatusCode = 301
                $res.RedirectLocation = '/duel/'
                $bytes = [byte[]]@()
                $type = 'text/plain'
            } elseif ($path -eq '/' -or $path -eq '/index.html') {
                $bytes = [Text.Encoding]::UTF8.GetBytes((Get-Page))
                $type = $types['.html']
            } else {
                $rel = $path.TrimStart('/')
                if ($rel -eq 'duel/') { $rel = 'duel/index.html' }
                $rel = $rel.Replace('/', '\')
                $ours = $rel -eq 'fp10-bridge.js' -or $rel.StartsWith('duel\')
                $file = if ($ours) { Join-Path $here $rel } else { Join-Path $neokeys $rel }
                $full = [IO.Path]::GetFullPath($file)
                if (-not $full.StartsWith($here, [StringComparison]::OrdinalIgnoreCase) -or
                    -not (Test-Path $full -PathType Leaf)) {
                    $res.StatusCode = 404
                    $bytes = [Text.Encoding]::UTF8.GetBytes('not found')
                    $type = 'text/plain'
                } else {
                    $bytes = [IO.File]::ReadAllBytes($full)
                    $type = $types[[IO.Path]::GetExtension($full).ToLower()]
                    if (-not $type) { $type = 'application/octet-stream' }
                }
            }
            $res.ContentType = $type
            $res.Headers['Cache-Control'] = 'no-cache'
            $res.ContentLength64 = $bytes.Length
            $res.OutputStream.Write($bytes, 0, $bytes.Length)
        } catch {
            Write-Warning "$path : $_"
        } finally {
            $res.Close()
        }
    }
} finally {
    $listener.Stop()
}
