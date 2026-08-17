<#
Creates (or overwrites) a Start Menu shortcut carrying a custom AppUserModelID (AUMID),
which Windows requires before a toast notification from this app is allowed to render
interactive elements (buttons/inputs).

Two-step approach, chosen after live debugging during Tier A build:
  1. Create the plain shortcut via the well-tested WScript.Shell COM object.
  2. Apply the AppUserModelID property afterwards via SHGetPropertyStoreFromParsingName.
An earlier version tried to do both via a single hand-rolled IShellLinkW -> IPropertyStore
QueryInterface cast (Add-Type C# COM interop) and reliably threw
"ArgumentException: Value does not fall within the expected range" from ShellLink's property
store cast — never wrote the file. Splitting shortcut creation from property-setting avoids
that cast entirely and was confirmed working live (shortcut persists, SetValue/Commit succeed,
actionable toast buttons render under the resulting AUMID).
#>
param(
    [Parameter(Mandatory = $true)][string]$ShortcutPath,
    [Parameter(Mandatory = $true)][string]$TargetPath,
    [string]$Arguments = "",
    [Parameter(Mandatory = $true)][string]$AppUserModelId
)

$wshell = New-Object -ComObject WScript.Shell
$shortcut = $wshell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $TargetPath
$shortcut.Arguments = $Arguments
$shortcut.Save()

Add-Type @"
using System;
using System.Runtime.InteropServices;

[StructLayout(LayoutKind.Sequential, Pack = 4)]
public struct PROPERTYKEY
{
    public Guid fmtid;
    public uint pid;
    public PROPERTYKEY(Guid fmtid, uint pid) { this.fmtid = fmtid; this.pid = pid; }
}

[StructLayout(LayoutKind.Explicit, Size = 16)]
public struct PROPVARIANT
{
    [FieldOffset(0)] public ushort vt;
    [FieldOffset(8)] public IntPtr pointerValue;
}

[ComImport]
[Guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPropertyStore
{
    void GetCount(out uint cProps);
    void GetAt(uint iProp, out PROPERTYKEY pkey);
    void GetValue(ref PROPERTYKEY key, out PROPVARIANT pv);
    void SetValue(ref PROPERTYKEY key, ref PROPVARIANT pv);
    void Commit();
}

public static class NativeMethods
{
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    public static extern void SHGetPropertyStoreFromParsingName(
        string pszPath,
        IntPtr pbc,
        int flags,
        ref Guid riid,
        [MarshalAs(UnmanagedType.Interface)] out IPropertyStore propertyStore);
}

public static class AppIdSetter
{
    public static void Apply(string path, string aumid)
    {
        Guid iidPropStore = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99");
        IPropertyStore propStore;
        // flags=2 (GPS_READWRITE)
        NativeMethods.SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, 2, ref iidPropStore, out propStore);

        var pkey = new PROPERTYKEY(new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), 5);
        var pv = new PROPVARIANT();
        pv.vt = 31; // VT_LPWSTR
        pv.pointerValue = Marshal.StringToCoTaskMemUni(aumid);

        propStore.SetValue(ref pkey, ref pv);
        propStore.Commit();
        Marshal.ReleaseComObject(propStore);
    }
}
"@

[AppIdSetter]::Apply($ShortcutPath, $AppUserModelId)
Write-Output "Shortcut created: $ShortcutPath (AUMID: $AppUserModelId)"
