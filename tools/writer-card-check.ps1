[CmdletBinding(DefaultParameterSetName='Physical')]
param(
 [Parameter(Mandatory=$true)][string]$ImagePath,
 [Parameter(Mandatory=$true,ParameterSetName='Physical')][int]$DiskNumber,
 [Parameter(Mandatory=$true,ParameterSetName='File')][string]$CardImagePath,
 [string]$OutFolder=(Join-Path $PWD 'banana-writer-check')
)
$ErrorActionPreference='Stop'
if([IO.Path]::GetExtension($ImagePath) -ne '.img'){throw 'Select the uncompressed .img file.'}
$ImagePath=(Resolve-Path -LiteralPath $ImagePath).Path
if($PSCmdlet.ParameterSetName -eq 'Physical'){
 $disk=Get-Disk -Number $DiskNumber
 if($disk.IsSystem -or $disk.IsBoot){throw 'A system disk cannot be selected.'}
 if($disk.BusType -notin @('USB','SD','MMC')){throw 'Select a USB/SD/MMC card reader.'}
 $cardPath='\\.\PhysicalDrive'+$DiskNumber
 $cardSize=[int64]$disk.Size
}else{
 $cardPath=(Resolve-Path -LiteralPath $CardImagePath).Path
 $cardSize=(Get-Item -LiteralPath $cardPath).Length
}
# Both handles are read-only. No partition, filesystem or device metadata is changed.
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Security.Cryptography;
public static class BananaWriterCheck {
 public static byte[] Read(Stream s,long offset,int count) {
  s.Position=offset;byte[] b=new byte[count];int done=0;
  while(done<count){int n=s.Read(b,done,count-done);if(n==0)throw new EndOfStreamException();done+=n;}return b;
 }
 public static long First(byte[] a,byte[] b,int from,int length){
  for(int i=from;i<from+length;i++)if(a[i]!=b[i])return i;return -1;
 }
 public static string Hash(Stream s,long offset,long count){
  s.Position=offset;byte[] b=new byte[1048576];
  using(SHA256 h=SHA256.Create()){
   while(count>0){int n=s.Read(b,0,(int)Math.Min(count,b.Length));if(n==0)throw new EndOfStreamException();h.TransformBlock(b,0,n,b,0);count-=n;}
   h.TransformFinalBlock(new byte[0],0,0);return BitConverter.ToString(h.Hash).Replace("-", "").ToLowerInvariant();
  }
 }
}
'@
$image=[IO.File]::Open($ImagePath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
$card=$null
try{
 $card=[IO.File]::Open($cardPath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
 if($cardSize -lt $image.Length){throw 'Card/dump is smaller than the reference image.'}
 $headImage=[BananaWriterCheck]::Read($image,0,16777216)
 $headCard=[BananaWriterCheck]::Read($card,0,16777216)
 if([Text.Encoding]::ASCII.GetString($headImage,512,8) -ne 'EFI PART'){throw 'Reference has no GPT header.'}
 New-Item -ItemType Directory -Force -Path $OutFolder | Out-Null
 $OutFolder=(Resolve-Path -LiteralPath $OutFolder).Path
 [IO.File]::WriteAllBytes((Join-Path $OutFolder 'card-first-16MiB.bin'),$headCard)
 $regions=@()
 foreach($r in @(@('MBR',0,512),@('GPT',512,32256),@('Rockchip-loader',32768,16744448))){
  $first=[BananaWriterCheck]::First($headImage,$headCard,[int]$r[1],[int]$r[2])
  $regions += [pscustomobject]@{region=$r[0];match=($first -eq -1);first_different_offset=$first}
 }
 $entryLba=[BitConverter]::ToUInt64($headImage,584)
 $count=[BitConverter]::ToUInt32($headImage,592)
 $entrySize=[BitConverter]::ToUInt32($headImage,596)
 if($count -gt 128 -or $entrySize -lt 128 -or ($entryLba*512+$count*$entrySize) -gt $headImage.Length){throw 'Unsupported GPT entry array.'}
 $partitions=@()
 for($i=0;$i -lt $count;$i++){
  $p=[int]($entryLba*512+$i*$entrySize)
  $first=[BitConverter]::ToUInt64($headImage,$p+32)
  $last=[BitConverter]::ToUInt64($headImage,$p+40)
  if($first -eq 0){continue}
  $name=[Text.Encoding]::Unicode.GetString($headImage,$p+56,72).Trim([char]0)
  $offset=[int64]$first*512;$length=[int64]($last-$first+1)*512
  if($last -lt $first -or $offset+$length -gt $image.Length){throw 'Invalid reference partition.'}
  $ih=[BananaWriterCheck]::Hash($image,$offset,$length)
  $ch=[BananaWriterCheck]::Hash($card,$offset,$length)
  $partitions += [pscustomobject]@{name=$name;offset=$offset;length=$length;image_sha256=$ih;card_sha256=$ch;match=($ih -eq $ch)}
 }
 $report=[pscustomobject]@{reference_image=[IO.Path]::GetFileName($ImagePath);image_size=$image.Length;card_size=$cardSize;regions=$regions;partitions=$partitions;note='Read immediately after writing, before first handheld boot. GPT-only changes can be Windows repairs; loader/payload changes need investigation.'}
 $report | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $OutFolder 'writer-comparison.json')
 $regions | Format-Table
 $partitions | Select-Object name,match | Format-Table
 Write-Host ('Report: '+(Join-Path $OutFolder 'writer-comparison.json'))
}finally{
 if($card){$card.Dispose()};$image.Dispose()
}
