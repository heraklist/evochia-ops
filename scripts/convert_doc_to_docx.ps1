param(
  [Parameter(Mandatory=$true)][string]$InputPath,
  [Parameter(Mandatory=$true)][string]$OutDir
)

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# Attempt Word COM conversion first
try {
  $word = New-Object -ComObject Word.Application
  $word.Visible = $false
  $doc = $word.Documents.Open((Resolve-Path $InputPath).Path)
  $base = [System.IO.Path]::GetFileNameWithoutExtension($InputPath)
  $out = Join-Path $OutDir ($base + '.docx')
  $doc.SaveAs([ref]$out, [ref]16) # wdFormatXMLDocument
  $doc.Close()
  $word.Quit()
  Write-Output $out
  exit 0
} catch {
  Write-Output "WORD_COM_FAILED"
}

# Fallback to soffice if available
$soffice = Get-Command soffice -ErrorAction SilentlyContinue
if ($soffice) {
  & $soffice.Path --headless --convert-to docx --outdir $OutDir $InputPath
  exit 0
}

Write-Error "Could not convert .doc to .docx (Word COM and soffice unavailable)."
exit 1
