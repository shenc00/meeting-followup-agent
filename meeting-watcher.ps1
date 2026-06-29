#Requires -Version 5.1
<#
.SYNOPSIS
  Background watcher: auto-triggers sync-todos-onenote.bat when a Teams meeting ends.
  Polls Outlook Calendar every 2 minutes. Waits WAIT_MINUTES after scheduled end
  before triggering, giving the facilitator time to finalise Loop notes.
  Run once via start-watcher.bat; register at startup via register-at-startup.bat.
#>

param()
Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$SCRIPT_DIR     = Split-Path -Parent $MyInvocation.MyCommand.Definition
$SYNC_PS1       = Join-Path $SCRIPT_DIR "sync_onenote.ps1"
$PROCESSED_FILE = Join-Path $SCRIPT_DIR "data\processed_meetings.json"
$LOG_FILE       = Join-Path $SCRIPT_DIR "data\watcher.log"
$WAIT_MINUTES   = 5    # minutes after meeting scheduled end before syncing
$POLL_SECONDS   = 120  # how often to poll calendar (seconds)
$LOOKBACK_HOURS = 2    # how far back to look for ended meetings

function Write-Log([string]$msg) {
    $line = ("[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] " + $msg)
    Write-Host $line
    Add-Content -Path $LOG_FILE -Value $line -ErrorAction SilentlyContinue
}

# Ensure data dir exists
New-Item -ItemType Directory -Force -Path (Split-Path $PROCESSED_FILE) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $LOG_FILE)       | Out-Null

# Load already-processed meeting IDs
function Load-Processed {
    if (Test-Path $PROCESSED_FILE) {
        try {
            $j = Get-Content $PROCESSED_FILE -Raw | ConvertFrom-Json
            $h = @{}
            $j.PSObject.Properties | ForEach-Object { $h[$_.Name] = $_.Value }
            return $h
        } catch {}
    }
    return @{}
}

function Save-Processed([hashtable]$ids) {
    $ids | ConvertTo-Json | Set-Content $PROCESSED_FILE -Encoding UTF8
}

Write-Log "=== Meeting Follow-Up Watcher started ==="
Write-Log ("Watching for Teams meetings; will sync " + $WAIT_MINUTES + " min after each ends.")

$processedIds = Load-Processed

while ($true) {
    try {
        $now    = Get-Date
        $cutoff = $now.AddHours(-$LOOKBACK_HOURS)

        $outlook  = New-Object -ComObject Outlook.Application
        $ns       = $outlook.GetNamespace("MAPI")
        $calendar = $ns.GetDefaultFolder(9)
        $items    = $calendar.Items
        $items.Sort("[End]", $false)
        $items.IncludeRecurrences = $true

        foreach ($item in $items) {
            try {
                $endTime   = [datetime]$item.End
                $startTime = [datetime]$item.Start

                # Only meetings that ended within our lookback window
                if ($endTime -gt $now)    { continue }
                if ($endTime -lt $cutoff) { break }
                if ($startTime -gt $now)  { continue }

                $meetingId = $item.GlobalAppointmentID
                if ($processedIds.ContainsKey($meetingId)) { continue }

                # Detect Teams meetings: check OnlineMeetingURL or body keywords
                $isTeams = $false
                try { $isTeams = ($item.OnlineMeetingURL -ne "") } catch {}
                if (-not $isTeams) {
                    $bodyText = (($item.Body + " " + $item.Location).ToLower())
                    $isTeams  = ($bodyText -match "teams\.microsoft\.com|/l/meetup")
                }
                if (-not $isTeams) { continue }

                $subject = $item.Subject
                Write-Log ("Teams meeting just ended: '" + $subject + "' (ended " + $endTime.ToString("HH:mm") + ")")

                # Mark as queued so we don't process again on next poll
                $processedIds[$meetingId] = $endTime.ToString("o")
                Save-Processed $processedIds

                # Wait for facilitator to finish Loop notes
                Write-Log ("  Waiting " + $WAIT_MINUTES + " minutes for Loop notes to be finalised...")
                Start-Sleep -Seconds ($WAIT_MINUTES * 60)

                # Trigger the sync (visible window so user can see progress)
                Write-Log ("  Triggering sync for: '" + $subject + "'")
                $env:OPENAI_API_KEY = [System.Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "User")
                Start-Process "powershell.exe" -ArgumentList (
                    "-NoProfile -ExecutionPolicy Bypass -File `"" + $SYNC_PS1 + "`" -MeetingTitle `"" + $subject + "`""
                ) -WindowStyle Normal

            } catch { continue }
        }

    } catch {
        Write-Log ("Calendar error: " + $_.Exception.Message)
    }

    Start-Sleep -Seconds $POLL_SECONDS
}