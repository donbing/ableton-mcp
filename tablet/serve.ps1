# Serve NeoKeys with the FP10 Lights bridge on http://localhost (a secure context, so Chrome allows Web MIDI).
# NeoKeys' index.html is served with fp10-bridge.js, claude-me.js, lights-layers.js and panel-folds.js added and
# its Cloudflare analytics beacon removed; the file on disk is never changed. Duel (duel/) is served as it is, on
# /duel/. Works in Windows PowerShell 5.1 and PowerShell 7, nothing to install.
#
#   powershell -ExecutionPolicy Bypass -File serve.ps1 [-Port 8765] [-NoBrowser] [-Open duel/]
#
# "Claude me" lesson plans: POST /api/claude-me/plan forwards the page's song summary to the Claude API with the
# key from ANTHROPIC_API_KEY (process or user environment), so the key never reaches the page. Only pages
# served from here may call it. CLAUDE_ME_MODEL overrides the model; CLAUDE_ME_API_URL the endpoint (tests).
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
    $tag = '<script src="/fp10-bridge.js"></script>' + "`n" +
           '<script src="https://cdn.jsdelivr.net/npm/tonal@6.4.2/browser/tonal.min.js"></script>' + "`n" +
           '<script src="/claude-me.js"></script>' + "`n" +
           '<script src="/lights-layers.js"></script>' + "`n" +
           '<script src="/panel-folds.js"></script>'
    $at = $html.LastIndexOf('</body>')
    if ($at -lt 0) { return $html + $tag }
    return $html.Insert($at, $tag + "`n")
}

# ---- Claude me: lesson plans from the Claude API, key kept here ----
$own = @('fp10-bridge.js', 'claude-me.js', 'lights-layers.js', 'panel-folds.js')
$claudeModel = if ($env:CLAUDE_ME_MODEL) { $env:CLAUDE_ME_MODEL } else { 'claude-opus-5-5' }
$claudeUrl = if ($env:CLAUDE_ME_API_URL) { $env:CLAUDE_ME_API_URL } else { 'https://api.anthropic.com/v1/messages' }
$planSchema = [IO.File]::ReadAllText((Join-Path $here 'claude-me-plan.schema.json'), [Text.Encoding]::UTF8)
$planSystem = @'
You are a piano teacher planning short practice lessons for one song in NeoKeys, a falling-notes app with a
practice mode that waits until the learner plays the right notes. You get a summary of the song (key, tempo,
bars, form, chords per half bar, hand ranges, note onsets per bar) and the learner's recent runs, if any.
Plan 3 to 12 lessons, easiest first: learn each new section (not repeats of one) in small pieces, one hand
before two, simplified (melody, block chords) before as written, slow before fast; finish with the whole song.
Use the runs: repeat or slow down what failed and mention weak bars, skip what was passed easily. Keep bars
inside the song and lessons 2 to 8 bars long, except the final whole-song lessons. Write titles and the coach
note in plain, friendly English.
'@
Add-Type -AssemblyName System.Net.Http
$http = New-Object Net.Http.HttpClient
$http.Timeout = [TimeSpan]::FromSeconds(240)

function Get-ClaudeKey {
    if ($env:ANTHROPIC_API_KEY) { return $env:ANTHROPIC_API_KEY }
    return [Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY', 'User')
}

function Send-Claude([string]$body, [string]$key, [bool]$fallback) {
    $req = New-Object Net.Http.HttpRequestMessage([Net.Http.HttpMethod]::Post, $claudeUrl)
    $req.Headers.Add('x-api-key', $key)
    $req.Headers.Add('anthropic-version', '2023-06-01')
    if ($fallback) { $req.Headers.Add('anthropic-beta', 'server-side-fallback-2026-07-01') }
    $req.Content = New-Object Net.Http.StringContent($body, [Text.Encoding]::UTF8, 'application/json')
    $resp = $http.SendAsync($req).Result
    return @{ Status = [int]$resp.StatusCode; Text = $resp.Content.ReadAsStringAsync().Result }
}

# Returns the HTTP status and the JSON text for the page.
function Get-LessonPlan([string]$requestJson) {
    $key = Get-ClaudeKey
    if (-not $key) { return 503, '{"error":"no ANTHROPIC_API_KEY on the computer running serve.ps1"}' }
    if ($requestJson.Length -gt 200000) { return 413, '{"error":"song summary too large"}' }
    try { $in = $requestJson | ConvertFrom-Json } catch { return 400, '{"error":"bad JSON"}' }
    if (-not $in.summary -or -not $in.summary.bars) { return 400, '{"error":"no song summary"}' }

    $user = "Song summary and the learner's recent runs, as JSON:`n" + $requestJson
    $head = '{"model":' + (ConvertTo-Json $claudeModel) + ',"max_tokens":16000,' +
            '"output_config":{"effort":"medium","format":{"type":"json_schema","schema":' + $planSchema + '}},' +
            '"system":' + (ConvertTo-Json $planSystem) + ',' +
            '"messages":[{"role":"user","content":' + (ConvertTo-Json $user) + '}]'
    $started = Get-Date
    try {
        $r = Send-Claude ($head + ',"fallbacks":"default"}') $key $true
        # Refusal fallback is a beta: if this account or endpoint rejects it, ask again without.
        if ($r.Status -eq 400 -and $r.Text -match 'fallback') { $r = Send-Claude ($head + '}') $key $false }
    } catch {
        return 502, ('{"error":' + (ConvertTo-Json ("can't reach the Claude API: " + $_.Exception.GetBaseException().Message)) + '}')
    }
    if ($r.Status -ne 200) {
        $msg = try { ($r.Text | ConvertFrom-Json).error.message } catch { $r.Text }
        Write-Warning "Claude me: API $($r.Status): $msg"
        return 502, ('{"error":' + (ConvertTo-Json ("Claude API " + $r.Status + ": " + $msg)) + '}')
    }
    $out = $r.Text | ConvertFrom-Json
    if ($out.stop_reason -eq 'refusal') { return 502, '{"error":"Claude declined to plan this song"}' }
    if ($out.stop_reason -eq 'max_tokens') { return 502, '{"error":"the plan was cut off (max_tokens)"}' }
    $text = ($out.content | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text }) -join ''
    try { $null = $text | ConvertFrom-Json } catch { return 502, '{"error":"Claude returned no plan"}' }
    Write-Host ("Claude me: plan for {0} from {1} in {2:n0} s" -f $in.summary.title, $out.model, ((Get-Date) - $started).TotalSeconds)
    return 200, ('{"plan":' + $text + '}')
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
            if ($path -like '/api/claude-me/*') {
                # Only NeoKeys as served from here: other sites open in the browser can't spend the key.
                $origin = $ctx.Request.Headers['Origin']
                $status = 200
                if ($origin -and $origin -ne "http://localhost:$Port") {
                    $status, $json = 403, '{"error":"forbidden"}'
                } elseif ($path -eq '/api/claude-me/status') {
                    $json = '{"key":' + ([bool](Get-ClaudeKey)).ToString().ToLower() + ',"model":' + (ConvertTo-Json $claudeModel) + '}'
                } elseif ($path -eq '/api/claude-me/plan' -and $ctx.Request.HttpMethod -eq 'POST' -and $origin) {
                    $reader = New-Object IO.StreamReader($ctx.Request.InputStream, [Text.Encoding]::UTF8)
                    $status, $json = Get-LessonPlan $reader.ReadToEnd()
                } else {
                    $status, $json = 404, '{"error":"not found"}'
                }
                $res.StatusCode = $status
                $bytes = [Text.Encoding]::UTF8.GetBytes($json)
                $type = $types['.json']
            } elseif ($path -eq '/duel') {
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
                $ours = ($own -contains $rel) -or $rel.StartsWith('duel\')
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
