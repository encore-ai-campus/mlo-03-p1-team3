# Configure one dedicated bridge; never restore VMware network defaults.
# Registry/ABI reference: https://github.com/fl0l0u/vmnet-cli (Apache-2.0).
param([string]$Gateway, [int]$Vnet=2, [string]$Prefix='podobank')
$ProgressPreference='SilentlyContinue'
$ErrorActionPreference='Stop'
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if($Vnet -lt 2 -or $Vnet -gt 19 -or $Vnet -eq 8){throw 'Use a dedicated VMnet2..19 excluding VMnet8'}
$route=Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Where-Object NextHop -eq $Gateway | Sort-Object RouteMetric | Select-Object -First 1
if(-not $route){throw 'No Windows default route matches the selected LAN gateway'}
$adapter=Get-NetAdapter -InterfaceIndex $route.InterfaceIndex
if($adapter.Status -ne 'Up'){throw 'Selected bridge adapter is not active'}
$vmrun='C:\Program Files\VMware\VMware Workstation\vmrun.exe'
$name="vmnet$Vnet"
$cfg="HKLM:\SOFTWARE\VMware, Inc.\VMnetLib\VMnetConfig\$name"
$pinRoot='HKLM:\SYSTEM\CurrentControlSet\Services\VMnetBridge\Parameters\Adapters'
$guid=([guid]$adapter.InterfaceGuid).ToString('B').ToUpper()
$pin="$pinRoot\$guid"
$marker='PodoBank bridged LAN'
$existing=Get-ItemProperty $cfg -ErrorAction SilentlyContinue
if($existing.DisplayName -and $existing.DisplayName -ne $marker -and $existing.DisplayName -ne "VMnet$Vnet"){throw 'Selected VMnet is owned by another configuration'}
$featuresMatch=$true
foreach($feature in @('Adapter','NAT','DHCP')){
 $value=Get-ItemProperty "$cfg\$feature" -ErrorAction SilentlyContinue
 if($value."Use$feature" -eq 1){throw 'Selected VMnet already has a host adapter, DHCP or NAT'}
 if($null -eq $value."Use$feature" -or $value."Use$feature" -ne 0){$featuresMatch=$false}
}
$priorPin=Get-ItemProperty $pin -ErrorAction SilentlyContinue
if($null -ne $priorPin.VMnet -and $priorPin.VMnet -ne $Vnet){throw 'Physical adapter already belongs to a different explicit bridge'}
$driverState=(Get-CimInstance Win32_SystemDriver -Filter "Name='VMnetBridge'").State
if($featuresMatch -and $priorPin.VMnet -eq $Vnet -and $driverState -eq 'Running'){
 [pscustomobject]@{Bridge="VMnet$Vnet";Adapter=$adapter.Name;Gateway=$Gateway;AlreadyConfigured=$true}|ConvertTo-Json -Compress
 exit 0
}
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
 throw 'Run this bridge setup once from Windows PowerShell as Administrator. No network settings changed.'
}
$running=@(& $vmrun list | Select-Object -Skip 1 | Where-Object {$_ -and $_.Trim()})
if($running.Count -gt 0){throw 'Stop running VMs before changing the bridge driver'}
# A global driver cycle affects only VMware bridging. Windows TCP/IP stays enabled.
& sc.exe stop VMnetBridge | Out-Null
if($LASTEXITCODE -notin @(0,1062)){throw 'Cannot stop bridge driver safely'}
$deadline=(Get-Date).AddSeconds(30)
while((Get-CimInstance Win32_SystemDriver -Filter "Name='VMnetBridge'").State -ne 'Stopped'){
 if((Get-Date) -gt $deadline){throw 'Bridge driver stop timed out'}
 Start-Sleep -Milliseconds 300
}
try {
 New-Item -Path $cfg -Force | Out-Null
 New-ItemProperty -Path $cfg -Name DisplayName -Value $marker -PropertyType String -Force | Out-Null
 foreach($feature in @('Adapter','NAT','DHCP')){
  New-Item -Path "$cfg\$feature" -Force | Out-Null
  New-ItemProperty -Path "$cfg\$feature" -Name "Use$feature" -Value 0 -PropertyType DWord -Force | Out-Null
 }
 New-Item -Path $pin -Force | Out-Null
 New-ItemProperty -Path $pin -Name VMnet -Value $Vnet -PropertyType DWord -Force | Out-Null
} finally {
 & sc.exe start VMnetBridge | Out-Null
 if($LASTEXITCODE -notin @(0,1056)){throw 'Bridge driver did not restart'}
}
[pscustomobject]@{Bridge="VMnet$Vnet";Adapter=$adapter.Name;Description=$adapter.InterfaceDescription;Gateway=$Gateway}|ConvertTo-Json -Compress
