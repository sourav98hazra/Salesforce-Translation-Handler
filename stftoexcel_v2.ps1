$inputFile = "Outdated and untranslated_ja_2026-05-25 0751.stf"
$outputExcel = "STF_Organized_PiDev.xlsx"
$dataBySheet = @{}

# 🧾 Step 1: Parse input file
$lines = Get-Content $inputFile -Encoding UTF8 | Where-Object { $_ -match "\S" -and $_ -notmatch "^[-#]" }

foreach ($line in $lines) {
    $parts = $line -split "`t"

    if ($parts.Count -lt 2) { continue }

    $key         = $parts[0]
    $label       = $parts[1]
    $translation = if ($parts.Count -ge 3) { $parts[2] } else { "" }

    # Determine component type from key
    $componentType = $key -split "\." | Select-Object -First 1
    if (-not $componentType) { $componentType = "Unknown" }

    # Determine translation status
    $status = if ($translation -and $translation.Trim() -ne "") { "Translated" } else { "Untranslated" }

    $logicalSheetName = "${componentType}_${status}"

    $entry = [PSCustomObject]@{
        Key         = $key
        Label       = $label
        Translation = $translation
    }

    if (-not $dataBySheet.ContainsKey($logicalSheetName)) {
        $dataBySheet[$logicalSheetName] = @()
    }

    $dataBySheet[$logicalSheetName] += $entry
}

# Remove old Excel if exists
if (Test-Path $outputExcel) {
    Remove-Item $outputExcel
}

# 🧾 Step 2: Export organized sheets to Excel with unique names
$sheetNameMap = @{}
$usedSheetNames = @{}

foreach ($logicalSheet in $dataBySheet.Keys) {
    # Base name for Excel sheet: max 28 chars to allow room for suffix
    $baseName = if ($logicalSheet.Length -gt 28) { $logicalSheet.Substring(0, 28) } else { $logicalSheet }
    $actualSheetName = $baseName
    $i = 1

    while ($usedSheetNames.Contains($actualSheetName)) {
        $actualSheetName = "$baseName`_$i"
        $i++
    }

    $usedSheetNames[$actualSheetName] = $true
    $sheetNameMap[$logicalSheet] = $actualSheetName

    # Export sheet
    $dataBySheet[$logicalSheet] | Export-Excel -Path $outputExcel -WorksheetName $actualSheetName -AutoSize -Append
}

# 🧾 Step 3: Build Content Details summary sheet
$contentSummary = @()

foreach ($logicalSheet in $dataBySheet.Keys) {
    $splitName = $logicalSheet -split "_"
    $component = $splitName[0]
    $status    = $splitName[1]
    $count     = $dataBySheet[$logicalSheet].Count

    $row = [PSCustomObject]@{
        SheetName         = $logicalSheet
        SavedAs           = $sheetNameMap[$logicalSheet]
        ComponentType     = $component
        TranslationStatus = $status
        TotalRecords      = $count
    }

    $contentSummary += $row
}

# Export summary tab
$contentSummary | Export-Excel -Path $outputExcel -WorksheetName "Content Details" -AutoSize -Append

Write-Host "`n✅ Excel file created at: $outputExcel"
