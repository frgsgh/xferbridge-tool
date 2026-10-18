# Fetch POMs for seeded modules into localm2
$repo = "D:\Desktop\duobao\localm2"
function Group-Path([string]$g) { return $g -replace '\.', '/' }
$mods = @(
  @{g='net.minecraftforge'; a='forge'; v='1.20.1-47.3.0'},
  @{g='net.minecraftforge'; a='fmlcore'; v='1.20.1-47.3.0'},
  @{g='net.minecraftforge'; a='fmlloader'; v='1.20.1-47.3.0'},
  @{g='net.minecraftforge'; a='fmlearlydisplay'; v='1.20.1-47.3.0'},
  @{g='net.minecraftforge'; a='javafmllanguage'; v='1.20.1-47.3.0'},
  @{g='net.minecraftforge'; a='lowcodelanguage'; v='1.20.1-47.3.0'},
  @{g='net.minecraftforge'; a='mclanguage'; v='1.20.1-47.3.0'},
  @{g='net.minecraftforge'; a='accesstransformers'; v='8.0.4'},
  @{g='net.minecraftforge'; a='eventbus'; v='6.0.5'},
  @{g='net.minecraftforge'; a='forgespi'; v='7.0.1'},
  @{g='net.minecraftforge'; a='coremods'; v='5.1.6'},
  @{g='net.minecraftforge'; a='unsafe'; v='0.2.0'},
  @{g='net.minecraftforge'; a='mergetool'; v='1.1.5'},
  @{g='net.minecraftforge'; a='JarJarSelector'; v='0.3.19'},
  @{g='net.minecraftforge'; a='JarJarMetadata'; v='0.3.19'},
  @{g='net.minecraftforge'; a='JarJarFileSystems'; v='0.3.19'},
  @{g='net.minecraftforge'; a='binarypatcher'; v='1.1.1'},
  @{g='cpw.mods'; a='modlauncher'; v='10.0.9'},
  @{g='cpw.mods'; a='bootstraplauncher'; v='1.1.2'},
  @{g='cpw.mods'; a='securejarhandler'; v='2.1.10'},
  @{g='de.oceanlabs.mcp'; a='mcp_config'; v='1.20.1-20230612.114412'}
)
$bases = @("https://maven.creeperhost.net", "https://repo.spongepowered.org/maven", "https://maven.minecraftforge.net")
foreach ($en in $mods) {
  $dir = Join-Path $repo (Join-Path (Group-Path $en.g) (Join-Path $en.a $en.v))
  New-Item -ItemType Directory -Force $dir | Out-Null
  $pom = "$($en.a)-$($en.v).pom"
  $target = Join-Path $dir $pom
  if (Test-Path $target) { continue }
  foreach ($b in $bases) {
    $url = "$b/$(Group-Path $en.g)/$($en.a)/$($en.v)/$pom"
    try { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $target -TimeoutSec 60; "POM $pom"; break }
    catch { }
  }
}
"DONE"
