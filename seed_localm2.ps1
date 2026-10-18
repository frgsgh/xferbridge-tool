# Seed local maven repo D:\Desktop\duobao\localm2 from creeperhost mirror (stable fast path)
$repo = "D:\Desktop\duobao\localm2"
New-Item -ItemType Directory -Force $repo | Out-Null

function Group-Path([string]$g) { return $g -replace '\.', '/' }

$entries = @(
  @{g='net.minecraftforge'; a='forge'; v='1.20.1-47.3.0'; c=''; e='pom'},
  @{g='net.minecraftforge'; a='forge'; v='1.20.1-47.3.0'; c='userdev'; e='jar'},
  @{g='net.minecraftforge'; a='forge'; v='1.20.1-47.3.0'; c='universal'; e='jar'},
  @{g='net.minecraftforge'; a='forge'; v='1.20.1-47.3.0'; c='sources'; e='jar'},
  @{g='net.minecraftforge'; a='fmlcore'; v='1.20.1-47.3.0'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='fmlloader'; v='1.20.1-47.3.0'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='fmlearlydisplay'; v='1.20.1-47.3.0'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='javafmllanguage'; v='1.20.1-47.3.0'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='lowcodelanguage'; v='1.20.1-47.3.0'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='mclanguage'; v='1.20.1-47.3.0'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='client-extra'; v='1.20.1-47.3.0'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='accesstransformers'; v='8.0.4'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='eventbus'; v='6.0.5'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='forgespi'; v='7.0.1'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='coremods'; v='5.1.6'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='unsafe'; v='0.2.0'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='mergetool'; v='1.1.5'; c='api'; e='jar'},
  @{g='net.minecraftforge'; a='JarJarSelector'; v='0.3.19'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='JarJarMetadata'; v='0.3.19'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='JarJarFileSystems'; v='0.3.19'; c=''; e='jar'},
  @{g='net.minecraftforge'; a='binarypatcher'; v='1.1.1'; c='fatjar'; e='jar'},
  @{g='cpw.mods'; a='modlauncher'; v='10.0.9'; c=''; e='jar'},
  @{g='cpw.mods'; a='bootstraplauncher'; v='1.1.2'; c=''; e='jar'},
  @{g='cpw.mods'; a='securejarhandler'; v='2.1.10'; c=''; e='jar'},
  @{g='de.oceanlabs.mcp'; a='mcp_config'; v='1.20.1-20230612.114412'; c=''; e='zip'}
)

$bases = @("https://maven.creeperhost.net", "https://repo.spongepowered.org/maven", "https://maven.minecraftforge.net")
$fail = @()
foreach ($en in $entries) {
  $dir = Join-Path $repo (Join-Path (Group-Path $en.g) (Join-Path $en.a $en.v))
  New-Item -ItemType Directory -Force $dir | Out-Null
  $suffix = if ($en.c) { "-$($en.c)" } else { '' }
  $name = "$($en.a)-$($en.v)$suffix.$($en.e)"
  $target = Join-Path $dir $name
  if (Test-Path $target) { "SKIP $name"; continue }
  $ok = $false
  foreach ($b in $bases) {
    $url = "$b/$(Group-Path $en.g)/$($en.a)/$($en.v)/$name"
    try {
      Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $target -TimeoutSec 90
      "OK $name"
      $ok = $true
      break
    } catch {
      "try-fail $url :: $($_.Exception.Message)"
    }
  }
  if (-not $ok) { $fail += $name }
}
"----FAILURES----"
$fail | ForEach-Object { $_ }
"----DONE----"
