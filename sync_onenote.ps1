#Requires -Version 5.1
<#
.SYNOPSIS
    Reads the latest meeting todos from the agent database and appends them
    as a table to the "Meeting Minutes" section in OneNote.

.NOTES
    - Targets the fixed page "Action Items" inside the "Meeting Minutes" section.
    - Each run appends a new dated block — nothing is overwritten.
    - Run by double-clicking sync-todos-onenote.bat
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SCRIPT_DIR    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$DB_PATH       = Join-Path $SCRIPT_DIR "data\actions.json"
$SECTION_NAME  = "Meeting Minutes"
$PAGE_NAME     = "Action Items"
$ONE_NS        = "http://schemas.microsoft.com/office/onenote/2013/onenote"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Meeting Agent  |  Sync Latest Todos -> OneNote"           -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Load latest meeting tasks ─────────────────────────────────────────────

if (-not (Test-Path $DB_PATH)) {
    Write-Host "ERROR: $DB_PATH not found." -ForegroundColor Red
    Write-Host "Run 'meeting-agent from-file ...' first to generate tasks."
    exit 1
}

$db        = Get-Content $DB_PATH -Raw | ConvertFrom-Json
$tasksList = @()
$db.tasks.PSObject.Properties | ForEach-Object { $tasksList += $_.Value }

if ($tasksList.Count -eq 0) {
    Write-Host "No tasks found in database." -ForegroundColor Yellow
    exit 0
}

# Find the meeting with the most recent created_at
$latest    = $tasksList | Sort-Object created_at -Descending | Select-Object -First 1
$meetingId = $latest.meeting_id
$tasks     = $tasksList | Where-Object { $_.meeting_id -eq $meetingId }

try {
    $meetingDate = [datetime]$latest.created_at
} catch {
    $meetingDate = Get-Date
}

$meetingTitle = "Meeting $($meetingId.Substring(0, [Math]::Min(8, $meetingId.Length)))"

Write-Host "  Meeting  : $meetingTitle" -ForegroundColor White
Write-Host "  Date     : $($meetingDate.ToString('dd MMM yyyy'))" -ForegroundColor White
Write-Host "  Tasks    : $($tasks.Count)" -ForegroundColor White
Write-Host ""

# ── 2. Connect to OneNote ─────────────────────────────────────────────────────

Write-Host "  Connecting to OneNote..." -ForegroundColor Gray
try {
    $onenote = New-Object -ComObject "OneNote.Application"
} catch {
    Write-Host "ERROR: Could not connect to OneNote." -ForegroundColor Red
    Write-Host "Make sure OneNote is installed and open."
    exit 1
}

# ── 3. Find the "Meeting Minutes" section ─────────────────────────────────────

$hierXml = [string]::Empty
$onenote.GetHierarchy("", [Microsoft.Office.Interop.OneNote.HierarchyScope]::hsSections, [ref]$hierXml)
[xml]$hier = $hierXml

$section = $hier.SelectSingleNode(
    "//*[local-name()='Section'][@name='$SECTION_NAME']"
)

if ($null -eq $section) {
    Write-Host "ERROR: Section '$SECTION_NAME' not found in OneNote." -ForegroundColor Red
    Write-Host "Make sure the '$SECTION_NAME' tab exists and OneNote is open."
    exit 1
}

$sectionId = $section.ID
Write-Host "  Found section : '$SECTION_NAME'" -ForegroundColor Green

# ── 4. Find or create the "Action Items" page ─────────────────────────────────

$pagesXml = [string]::Empty
$onenote.GetHierarchy($sectionId, [Microsoft.Office.Interop.OneNote.HierarchyScope]::hsPages, [ref]$pagesXml)
[xml]$pages = $pagesXml

$page = $pages.SelectSingleNode(
    "//*[local-name()='Page'][@name='$PAGE_NAME']"
)

if ($null -eq $page) {
    Write-Host "  Creating page  : '$PAGE_NAME'" -ForegroundColor Yellow
    $newPageId = [string]::Empty
    $onenote.CreateNewPage($sectionId, [ref]$newPageId)

    # Set the page title
    $titleXml = @"
<?xml version="1.0"?>
<one:Page xmlns:one="$ONE_NS" ID="$newPageId">
  <one:Title>
    <one:OE><one:T><![CDATA[$PAGE_NAME]]></one:T></one:OE>
  </one:Title>
</one:Page>
"@
    $onenote.UpdatePageContent($titleXml)
    $pageId = $newPageId
} else {
    $pageId = $page.ID
    Write-Host "  Using page     : '$PAGE_NAME'" -ForegroundColor Green
}

# ── 5. Build table XML ────────────────────────────────────────────────────────

$dateLabel = $meetingDate.ToString("dd MMM yyyy  HH:mm")
$rowsXml   = ""

foreach ($t in $tasks) {
    $desc     = [System.Security.SecurityElement]::Escape(($t.description -replace '\s+', ' ').Trim())
    $ownerRaw = if ($t.owner -ne $null) { $t.owner } else { "TBD" }
    $owner    = [System.Security.SecurityElement]::Escape($ownerRaw)
    $priority = if ($t.priority -ne $null) { $t.priority.ToString().ToUpper() } else { "" }
    $status   = if ($t.status   -ne $null) { $t.status.ToString().ToUpper()   } else { "OPEN" }
    $due      = ""
    if ($t.due_date -ne $null) {
        try { $due = ([datetime]$t.due_date).ToString("dd MMM yyyy") } catch {}
    }

    $rowsXml += @"

          <one:Row>
            <one:Cell><one:OEChildren><one:OE><one:T><![CDATA[$desc]]></one:T></one:OE></one:OEChildren></one:Cell>
            <one:Cell><one:OEChildren><one:OE><one:T><![CDATA[$owner]]></one:T></one:OE></one:OEChildren></one:Cell>
            <one:Cell><one:OEChildren><one:OE><one:T><![CDATA[$due]]></one:T></one:OE></one:OEChildren></one:Cell>
            <one:Cell><one:OEChildren><one:OE><one:T><![CDATA[$priority]]></one:T></one:OE></one:OEChildren></one:Cell>
            <one:Cell><one:OEChildren><one:OE><one:T><![CDATA[$status]]></one:T></one:OE></one:OEChildren></one:Cell>
          </one:Row>
"@
}

$blockXml = @"
<?xml version="1.0"?>
<one:Page xmlns:one="$ONE_NS" ID="$pageId">
  <one:Outline>
    <one:OEChildren>
      <one:OE>
        <one:T><![CDATA[$meetingTitle  —  $dateLabel]]></one:T>
      </one:OE>
      <one:OE>
        <one:Table bordersVisible="true">
          <one:Columns>
            <one:Column index="0" width="240"/>
            <one:Column index="1" width="100"/>
            <one:Column index="2" width="95"/>
            <one:Column index="3" width="70"/>
            <one:Column index="4" width="80"/>
          </one:Columns>
          <one:Row>
            <one:Cell shadingColor="#1F4E79"><one:OEChildren><one:OE><one:T><![CDATA[Task]]></one:T></one:OE></one:OEChildren></one:Cell>
            <one:Cell shadingColor="#1F4E79"><one:OEChildren><one:OE><one:T><![CDATA[Owner]]></one:T></one:OE></one:OEChildren></one:Cell>
            <one:Cell shadingColor="#1F4E79"><one:OEChildren><one:OE><one:T><![CDATA[Due Date]]></one:T></one:OE></one:OEChildren></one:Cell>
            <one:Cell shadingColor="#1F4E79"><one:OEChildren><one:OE><one:T><![CDATA[Priority]]></one:T></one:OE></one:OEChildren></one:Cell>
            <one:Cell shadingColor="#1F4E79"><one:OEChildren><one:OE><one:T><![CDATA[Status]]></one:T></one:OE></one:OEChildren></one:Cell>
          </one:Row>$rowsXml
        </one:Table>
      </one:OE>
      <one:OE><one:T><![CDATA[]]></one:T></one:OE>
    </one:OEChildren>
  </one:Outline>
</one:Page>
"@

# ── 6. Append to page ─────────────────────────────────────────────────────────

$onenote.UpdatePageContent($blockXml)

Write-Host ""
Write-Host "  Done! $($tasks.Count) task(s) added to:" -ForegroundColor Green
Write-Host "  OneNote -> $SECTION_NAME -> $PAGE_NAME" -ForegroundColor Green
Write-Host ""
