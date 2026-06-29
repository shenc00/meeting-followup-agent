#Requires -Version 5.1
param(
    [string]$MeetingTitle = ""   # If passed by watcher, skips Outlook/manual prompt
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SCRIPT_DIR   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$DB_PATH      = Join-Path $SCRIPT_DIR "data\actions.json"
$CONFIG_PATH  = Join-Path $SCRIPT_DIR "config\config.yaml"
$VENV_PYTHON  = Join-Path $SCRIPT_DIR ".venv\Scripts\python.exe"
$SECTION_NAME = "Meeting Minutes"
$PAGE_NAME    = "Action Items"
$ONE_NS       = "http://schemas.microsoft.com/office/onenote/2013/onenote"

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Meeting Agent  |  Auto Sync Todos -> OneNote" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# --- STEP 1: Get latest meeting name from Outlook Calendar ---

Write-Host "[1/3] Reading Outlook Calendar for latest meeting..." -ForegroundColor Yellow

# If called by watcher with a known title, skip calendar lookup
if ($MeetingTitle -and $MeetingTitle.Trim() -ne "") {
    $meetingTitle = $MeetingTitle.Trim()
    Write-Host ("  Title provided by watcher: '" + $meetingTitle + "'") -ForegroundColor Green
} else {

$meetingTitle = $null
try {
    $outApp   = New-Object -ComObject Outlook.Application
    $ns       = $outApp.GetNamespace("MAPI")
    $calendar = $ns.GetDefaultFolder(9)
    $items    = $calendar.Items
    $items.Sort("[Start]", $true)
    $items.IncludeRecurrences = $true
    $now    = Get-Date
    $cutoff = $now.AddHours(-24)
    foreach ($item in $items) {
        try {
            $start = [datetime]$item.Start
            if ($start -lt $cutoff) { break }
            if ($start -gt $now)    { continue }
            $meetingTitle = $item.Subject
            Write-Host "  Found : '$meetingTitle'" -ForegroundColor Green
            Write-Host ("  Started : " + $start.ToString("HH:mm, dd MMM yyyy")) -ForegroundColor Gray
            break
        } catch { continue }
    }
} catch {
    Write-Host ("  WARNING: Could not read Outlook Calendar -- " + $_.Exception.Message) -ForegroundColor DarkYellow
}

}  # end else (watcher title bypass)

if (-not $meetingTitle) {
    Write-Host "  No recent meeting found in last 24h. Enter meeting title:" -ForegroundColor Yellow
    $meetingTitle = Read-Host "  Title"
    if (-not $meetingTitle) { Write-Host "Cancelled."; exit 0 }
}

Write-Host ""

# --- STEP 2: Extract notes -- try local OneDrive .loop file, then clipboard, then Outlook email ---

Write-Host "[2/3] Extracting action items from meeting notes..." -ForegroundColor Yellow

if (-not (Test-Path $VENV_PYTHON)) {
    Write-Host "ERROR: .venv not found. Run install.bat first." -ForegroundColor Red
    exit 1
}

$env:OPENAI_API_KEY = [System.Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "User")
$beforeRun = (Get-Date).AddMinutes(-3)
$exitCode  = 1

# Attempt 1: Open Loop page in Edge (already signed in -- no OAuth/admin needed)
# Construct SharePoint URL from OneDrive registry + local file path
$onedriveRoot = "$env:USERPROFILE\OneDrive - BD"
if (-not (Test-Path $onedriveRoot)) { $onedriveRoot = "$env:USERPROFILE\OneDrive" }

$loopFile = $null
$meetingsFolder = Join-Path $onedriveRoot "Meetings"
$searchRoot = if (Test-Path $meetingsFolder) { $meetingsFolder } else { $onedriveRoot }

if (Test-Path $searchRoot) {
    $cutoff    = (Get-Date).AddDays(-30)
    $keywords  = ($meetingTitle -split '\s+' | Where-Object { $_.Length -gt 2 } | Select-Object -First 3) -join '*'
    $loopFile  = Get-ChildItem -Path $searchRoot -Filter "*.loop" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $cutoff -and $_.BaseName -like "*$keywords*" } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $loopFile) {
        $firstWord = ($meetingTitle -split '\s+' | Where-Object { $_.Length -gt 2 } | Select-Object -First 1)
        $loopFile  = Get-ChildItem -Path $searchRoot -Filter "*.loop" -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -gt $cutoff -and $_.BaseName -like "*$firstWord*" } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
    }
}

if ($loopFile) {
    Write-Host ("  Found : " + $loopFile.BaseName) -ForegroundColor Green
    Add-Type -AssemblyName System.Windows.Forms

    # --- Strategy A: Read .loop bytes directly - no browser, no manual steps ---
    $loopText = $null
    Write-Host "  Reading .loop file from disk..." -ForegroundColor Gray
    try {
        $rawBytes  = [System.IO.File]::ReadAllBytes($loopFile.FullName)
        $rawText   = [System.Text.Encoding]::UTF8.GetString($rawBytes)
        $loopLines = $rawText -split "[\r\n]+"
        $goodLines = @()
        foreach ($ln in $loopLines) {
            $trimmed = $ln.Trim()
            if ($trimmed.Length -lt 10) { continue }
            # Skip CSS/style noise embedded by Loop page rendering
            if ($trimmed -match 'margin-bottom|margin-top|counter-reset|list-style-type|scriptor-list|listItem|font-size|padding') { continue }
            $alphaCount = ($trimmed -replace '[^A-Za-z]', '').Length
            if ($alphaCount -ge 6) { $goodLines += $trimmed }
        }
        $loopText = ($goodLines -join "`n").Trim()
        if ($loopText.Length -gt 100) {
            Write-Host ("  File: " + $loopText.Length + " chars extracted") -ForegroundColor Green
        } else {
            Write-Host "  File content too sparse - falling back to browser" -ForegroundColor Yellow
            $loopText = $null
        }
    } catch {
        Write-Host ("  File read error: " + $_.Exception.Message) -ForegroundColor DarkYellow
    }

    # --- Strategy B: Open browser + WScript automated Ctrl+A/Ctrl+C (no user prompt) ---
    if (-not $loopText) {
        $odReg    = Get-ItemProperty "HKCU:\Software\Microsoft\OneDrive\Accounts\Business1" -ErrorAction SilentlyContinue
        $spBase   = if ($odReg) { $odReg.ServiceEndpointUri -replace "/_api$", "" } else { "" }
        $odFolder = if ($odReg) { $odReg.UserFolder } else { $onedriveRoot }
        if ($spBase) {
            $relPath    = $loopFile.FullName.Substring($odFolder.Length + 1).Replace("\", "/")
            $loopWebUrl = $spBase + "/Documents/" + $relPath + "?Web=1"
            Write-Host ("  URL : " + $loopWebUrl) -ForegroundColor DarkGray
            $edgeExe = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            if (-not (Test-Path $edgeExe)) { $edgeExe = "msedge.exe" }
            Start-Process $edgeExe -ArgumentList "--new-window `"$loopWebUrl`""
            Write-Host "  Waiting 30s for Loop to render..." -ForegroundColor Yellow
            Start-Sleep -Seconds 30
            $wshell = New-Object -ComObject WScript.Shell
            $wshell.AppActivate("Microsoft Edge") | Out-Null
            Start-Sleep -Milliseconds 1500
            [System.Windows.Forms.Clipboard]::Clear()
            $wshell.SendKeys("^a")
            Start-Sleep -Milliseconds 800
            $wshell.SendKeys("^c")
            Start-Sleep -Milliseconds 1000
            $loopText = [System.Windows.Forms.Clipboard]::GetText()
            Write-Host ("  Browser: " + $loopText.Length + " chars") -ForegroundColor Gray
        }
    }

    if ($loopText -and $loopText.Trim().Length -gt 50) {
        $preview = $loopText.Substring(0, [Math]::Min(200, $loopText.Length)) -replace "`r`n", " "
        Write-Host ("  Preview : " + $preview) -ForegroundColor DarkGray
        Write-Host ("  Processing " + $loopText.Length + " chars...") -ForegroundColor Green
        [System.IO.File]::WriteAllText("$env:TEMP\loop_cap.txt", $loopText, [System.Text.Encoding]::UTF8)
        Push-Location $SCRIPT_DIR
        & $VENV_PYTHON -m meeting_agent.cli from-file --notes "$env:TEMP\loop_cap.txt" --title $meetingTitle
        $exitCode = $LASTEXITCODE
        Write-Host ("  Agent exit code: " + $exitCode) -ForegroundColor Gray
        Pop-Location
        Remove-Item "$env:TEMP\loop_cap.txt" -ErrorAction SilentlyContinue
    } else {
        Write-Host "  Could not extract Loop content from file or browser" -ForegroundColor Yellow
    }
}

if ($exitCode -ne 0) {
    # Attempt 2: clipboard (user copied Loop page with Ctrl+A, Ctrl+C)
    Add-Type -AssemblyName System.Windows.Forms
    $clipText = [System.Windows.Forms.Clipboard]::GetText()
    if ($clipText -and $clipText.Trim().Length -gt 50) {
        Write-Host "  [b] Loop content in clipboard -- processing..." -ForegroundColor Gray
        Push-Location $SCRIPT_DIR
        & $VENV_PYTHON -m meeting_agent.cli from-clipboard --title $meetingTitle
        $exitCode = $LASTEXITCODE
        Pop-Location
    }
}

if ($exitCode -ne 0) {
    # Attempt 3: Outlook email from facilitator
    Write-Host "  [c] Trying Outlook inbox (facilitator email)..." -ForegroundColor Gray
    $facilitatorEmail = ""
    if (Test-Path $CONFIG_PATH) {
        $configContent = Get-Content $CONFIG_PATH -Raw -Encoding UTF8
        if ($configContent -match 'facilitator:\s*[\r\n]+\s+email:\s+"([^"]+@[^"]+)"') {
            $facilitatorEmail = $Matches[1].Trim()
        }
    }
    $agentArgs = @("-m", "meeting_agent.cli", "fetch-notes", "--title", $meetingTitle)
    if ($facilitatorEmail) { $agentArgs += @("--facilitator", $facilitatorEmail) }
    Push-Location $SCRIPT_DIR
    & $VENV_PYTHON @agentArgs
    $exitCode = $LASTEXITCODE
    Pop-Location
}

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "  Could not find notes for '$meetingTitle'." -ForegroundColor Yellow
    Write-Host "  Options:" -ForegroundColor Yellow
    Write-Host "    1. Open the Loop page -> Ctrl+A -> Ctrl+C -> re-run" -ForegroundColor Yellow
    Write-Host "    2. Or use: meeting-agent from-loop --file [path-to-.loop-file]" -ForegroundColor Yellow
    exit 0
}

Write-Host ""

# --- STEP 3: Sync only tasks created in this run to OneNote ---

Write-Host "[3/3] Syncing todos to OneNote..." -ForegroundColor Yellow

if (-not (Test-Path $DB_PATH)) {
    Write-Host "ERROR: data/actions.json not found." -ForegroundColor Red
    exit 1
}

$db        = Get-Content $DB_PATH -Raw -Encoding UTF8 | ConvertFrom-Json
$tasksList = @()
$db.tasks.PSObject.Properties | ForEach-Object { $tasksList += $_.Value }

$tasks = @($tasksList | Where-Object {
    try { ([datetime]$_.created_at) -gt $beforeRun } catch { $false }
})

if ($tasks.Count -eq 0) {
    Write-Host "  No new tasks were extracted from this meeting." -ForegroundColor Yellow
    exit 0
}

try { $meetingDate = [datetime]($tasks | Select-Object -First 1).created_at } catch { $meetingDate = Get-Date }
Write-Host ("  New tasks : " + $tasks.Count) -ForegroundColor White

try {
    $onenote = New-Object -ComObject "OneNote.Application"
} catch {
    Write-Host ("ERROR: Could not connect to OneNote -- " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}

$hierXml = [string]::Empty
$onenote.GetHierarchy("", [Microsoft.Office.Interop.OneNote.HierarchyScope]::hsSections, [ref]$hierXml)
[xml]$hier = $hierXml

$xpathSection = "//*[local-name()='Section'][@name='" + $SECTION_NAME + "']"
$section = $hier.SelectSingleNode($xpathSection)
if ($null -eq $section) {
    Write-Host ("ERROR: Section '" + $SECTION_NAME + "' not found in OneNote.") -ForegroundColor Red
    exit 1
}
$sectionId = $section.ID
Write-Host ("  Section : '" + $SECTION_NAME + "' found") -ForegroundColor Green

$pagesXml = [string]::Empty
$onenote.GetHierarchy($sectionId, [Microsoft.Office.Interop.OneNote.HierarchyScope]::hsPages, [ref]$pagesXml)
[xml]$pages = $pagesXml

$xpathPage = "//*[local-name()='Page'][@name='" + $PAGE_NAME + "']"
$page = $pages.SelectSingleNode($xpathPage)
if ($null -eq $page) {
    $newPageId = [string]::Empty
    $onenote.CreateNewPage($sectionId, [ref]$newPageId)
    $titleXml = '<?xml version="1.0"?><one:Page xmlns:one="' + $ONE_NS + '" ID="' + $newPageId + '"><one:Title><one:OE><one:T><![CDATA[' + $PAGE_NAME + ']]></one:T></one:OE></one:Title></one:Page>'
    $onenote.UpdatePageContent($titleXml)
    $pageId = $newPageId
    Write-Host ("  Page : '" + $PAGE_NAME + "' created") -ForegroundColor Yellow
} else {
    $pageId = $page.ID
    Write-Host ("  Page : '" + $PAGE_NAME + "' found") -ForegroundColor Green
}

$dateLabel = $meetingDate.ToString("dd MMM yyyy  HH:mm")
$rowsXml = ""
foreach ($t in $tasks) {
    $desc     = [System.Security.SecurityElement]::Escape(($t.description -replace '\s+', ' ').Trim())
    $ownerRaw = if ($null -ne $t.owner) { $t.owner } else { "TBD" }
    $owner    = [System.Security.SecurityElement]::Escape($ownerRaw)
    $priority = if ($null -ne $t.priority) { $t.priority.ToString().ToUpper() } else { "" }
    $status   = if ($null -ne $t.status)   { $t.status.ToString().ToUpper()   } else { "OPEN" }
    $due = ""
    if ($null -ne $t.due_date) {
        try { $due = ([datetime]$t.due_date).ToString("dd MMM yyyy") } catch {}
    }
    $rowsXml += "<one:Row>" +
        "<one:Cell><one:OEChildren><one:OE><one:T><![CDATA[" + $desc + "]]></one:T></one:OE></one:OEChildren></one:Cell>" +
        "<one:Cell><one:OEChildren><one:OE><one:T><![CDATA[" + $owner + "]]></one:T></one:OE></one:OEChildren></one:Cell>" +
        "<one:Cell><one:OEChildren><one:OE><one:T><![CDATA[" + $due + "]]></one:T></one:OE></one:OEChildren></one:Cell>" +
        "<one:Cell><one:OEChildren><one:OE><one:T><![CDATA[" + $priority + "]]></one:T></one:OE></one:OEChildren></one:Cell>" +
        "<one:Cell><one:OEChildren><one:OE><one:T><![CDATA[" + $status + "]]></one:T></one:OE></one:OEChildren></one:Cell>" +
        "</one:Row>"
}

$hdrCell = '<one:Cell shadingColor="#1F4E79"><one:OEChildren><one:OE><one:T>'
$blockXml = '<?xml version="1.0"?>' +
    '<one:Page xmlns:one="' + $ONE_NS + '" ID="' + $pageId + '">' +
    '<one:Outline><one:OEChildren>' +
    '<one:OE><one:T><![CDATA[' + $meetingTitle + '  --  ' + $dateLabel + ']]></one:T></one:OE>' +
    '<one:OE><one:Table bordersVisible="true">' +
    '<one:Columns>' +
    '<one:Column index="0" width="240"/><one:Column index="1" width="100"/>' +
    '<one:Column index="2" width="95"/><one:Column index="3" width="70"/><one:Column index="4" width="80"/>' +
    '</one:Columns>' +
    '<one:Row>' +
    $hdrCell + '<![CDATA[Task]]></one:T></one:OE></one:OEChildren></one:Cell>' +
    $hdrCell + '<![CDATA[Owner]]></one:T></one:OE></one:OEChildren></one:Cell>' +
    $hdrCell + '<![CDATA[Due Date]]></one:T></one:OE></one:OEChildren></one:Cell>' +
    $hdrCell + '<![CDATA[Priority]]></one:T></one:OE></one:OEChildren></one:Cell>' +
    $hdrCell + '<![CDATA[Status]]></one:T></one:OE></one:OEChildren></one:Cell>' +
    '</one:Row>' +
    $rowsXml +
    '</one:Table></one:OE>' +
    '<one:OE><one:T><![CDATA[]]></one:T></one:OE>' +
    '</one:OEChildren></one:Outline>' +
    '</one:Page>'

$onenote.UpdatePageContent($blockXml)

Write-Host ""
Write-Host ("  Done! " + $tasks.Count + " new todo(s) added to:") -ForegroundColor Green
Write-Host ("  OneNote -> " + $SECTION_NAME + " -> " + $PAGE_NAME) -ForegroundColor Green
Write-Host ""
