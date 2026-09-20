"""Build the real embedded WPA core and exercise it under ASan/UBSan."""
import pathlib,re,subprocess,sys
root=pathlib.Path(__file__).resolve().parents[1]
app=root/'app/k7radio';out=root/'private/wpa-tests';out.mkdir(exist_ok=True,parents=True)
sources=re.findall(r'hostap/[^\s)]+\.c',(app/'hostap/sources.cmake').read_text())
flags=['-DCONFIG_NO_STDOUT_DEBUG','-DCONFIG_NO_WPA_MSG','-DCONFIG_NO_RANDOM_POOL','-DCONFIG_NO_RC4','-DCONFIG_NO_TKIP','-DCONFIG_SHA256','-DCONFIG_IEEE80211W','-DCONFIG_CRYPTO_INTERNAL','-DCONFIG_INTERNAL_AES','-DCONFIG_INTERNAL_SHA1','-DCONFIG_INTERNAL_SHA256','-DCONFIG_INTERNAL_MD5']
cmd=['gcc','-std=gnu11','-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined','-ffunction-sections','-fdata-sections','-Wl,--gc-sections',*flags,'-I'+str(app),'-I'+str(app/'hostap'),'-I'+str(app/'hostap/utils')]
cmd += [str(app/p) for p in sources]+[str(app/p) for p in ('skw_supplicant.c','skw_supplicant_os.c','skw_wpa_transport.c')]
cmd += [str(root/'tests/wifi/test_supplicant.c'),'-o',str(out/'test_supplicant')]
subprocess.run(cmd,check=True)
subprocess.run([str(out/'test_supplicant')],check=True)
