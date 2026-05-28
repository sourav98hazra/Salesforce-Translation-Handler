# Requires ImportExcel module

# Ask for Excel file name interactively
$inputExcel = Read-Host "Enter the Excel file name (with .xlsx extension)"

# Ask for language name interactively
$languageName = Read-Host "Enter the language name (e.g. Portuguese (European))"

# Define a mapping of language names to codes
$languageMap = @{
    "Portuguese (European)" = "pt_PT"
    "Portuguese (Brazilian)" = "pt_BR"
    "French"                 = "fr"
    "German"                 = "de"
    "Spanish"                = "es"
    "Italian"                = "it"
    "Dutch"                  = "nl"
    "Chinese (Simplified)"   = "zh_CN"
    "Chinese (Traditional)"  = "zh_TW"
    "Japanese"               = "ja"
    "Korean"                 = "ko"
}

# Try to auto-assign code, otherwise ask
if ($languageMap.ContainsKey($languageName)) {
    $languageCode = $languageMap[$languageName]
    Write-Host "✅ Language code auto-assigned: $languageCode"
} else {
    $languageCode = Read-Host "Enter the language code for $languageName"
}

# Define output file names logically
$outputFull     = "Super_STF_$languageCode.stf"
$outputUntrans  = "UntranslatedOnly_STF_$languageCode.stf"
$outputTrans    = "TranslatedOnly_STF_$languageCode.stf"

# Import content details sheet
$contentDetails = Import-Excel -Path $inputExcel -WorksheetName "Content Details"

# Initialize arrays
$fullLines        = @()
$untranslatedLines = @()
$translatedLines   = @()

# Metadata header for full file
$header = @"
# Language: $languageName
Language code: $languageCode
Type: Bilingual
Translation type: Metadata

------------------TRANSLATED-------------------
# KEY`tLABEL`tTRANSLATION`tOUT OF DATE
"@

$fullLines += $header
$translatedLines += "# KEY`tLABEL`tTRANSLATION`tOUT OF DATE"
$untranslatedLines += "# KEY`tLABEL"

# Process each worksheet
foreach ($entry in $contentDetails) {
    $sheetName = $entry.SavedAs
    $rows = Import-Excel -Path $inputExcel -WorksheetName $sheetName

    foreach ($row in $rows) {
        $key         = "$($row.Key)"
        $label       = "$($row.Label)"
        $translation = "$($row.Translation)".Trim()

        if ($translation -match '\S') {
            $line = "$key`t$label`t$translation`t-"
            $fullLines += $line
            $translatedLines += $line
        } else {
            $line = "$key`t$label"
            $fullLines += $line
            $untranslatedLines += $line
        }
    }
}

# Add untranslated section header to full file
$fullLines += ""
$fullLines += "------------------OUTDATED AND UNTRANSLATED-----------------"
$fullLines += ""
$fullLines += "# KEY`tLABEL"

# Write all three files with UTF-8 LF (no BOM)
[System.IO.File]::WriteAllText($outputFull, ($fullLines -join "`n"), [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($outputUntrans, ($untranslatedLines -join "`n"), [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($outputTrans, ($translatedLines -join "`n"), [System.Text.UTF8Encoding]::new($false))

Write-Host "`n✅ STF files created:"
Write-Host "• All records → $outputFull"
Write-Host "• Untranslated only → $outputUntrans"
Write-Host "• Translated only → $outputTrans"