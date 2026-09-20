import json
import re
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
INSPECTOR = HERE / "inspect.ps1"


def main() -> None:
    source = INSPECTOR.read_text(encoding="utf-8")
    forbidden = {
        "service mutation": r"\b(?:Restart|Stop|Start)-Service\b",
        "process termination": r"\b(?:Stop-Process|taskkill|kill)\b",
        "PnP mutation": r"(?i)pnputil(?:\.exe)?[^\n]*(?:/restart-device|/remove-device|/scan-devices|/disable-device|/enable-device)",
        "VM lifecycle/config mutation": r"(?i)vmrun[^\n]*(?:\sstart\s|\sstop\s|\sreset\s|writeVariable|connectNamedDevice|disconnectNamedDevice)",
        "udev mutation": r"(?i)udevadm\s+(?:trigger|control)",
        "registry/VMX mutation": r"\b(?:Set-ItemProperty|New-ItemProperty|Remove-ItemProperty)\b",
        "serial/Fastboot I/O": r"(?i)(?:serial\.Serial|fastboot_ram_download|fastboot\s+usb\s+1|\\\.\\COM\d+)",
    }
    violations = [name for name, pattern in forbidden.items() if re.search(pattern, source)]
    if violations:
        raise AssertionError(f"mutating operations found: {violations}")

    parser = (
        "$tokens=$null;$errors=$null;"
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{str(INSPECTOR).replace(chr(39), chr(39) * 2)}',"
        "[ref]$tokens,[ref]$errors)|Out-Null;"
        "if($errors.Count){$errors|ForEach-Object{$_.Message};exit 1}"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", parser],
        check=True,
    )

    report_path = HERE / "host-only-test.json"
    if report_path.exists():
        report_path.unlink()
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(INSPECTOR),
            "-SkipGuest",
            "-OutputPath",
            str(report_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema"] == "velavision.vmware-usb-readonly-diagnostic.v1"
    assert all(value is False for value in report["constraints"].values())
    assert report["guest"]["attempted"] is False
    assert isinstance(report["signals"]["vmware_service_running"], bool)

    result = {
        "schema": "velavision.vmware-usb-readonly-verification.v1",
        "powershell_parse": "pass",
        "forbidden_operation_scan": "pass",
        "host_only_execution": "pass",
        "report_schema": "pass",
        "inspector_sha256": __import__("hashlib").sha256(INSPECTOR.read_bytes()).hexdigest(),
    }
    (HERE / "verification.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
