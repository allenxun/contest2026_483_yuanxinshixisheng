from pathlib import Path
import hashlib,json
r=Path('/home/swl/openvela');w=r/'work/rk3576-preview'
p=r/'apps/examples/k7host/k7host_main.c'
before=p.read_bytes();backup=w/'k7host_main.c.prebench'
assert not backup.exists();backup.write_bytes(before)
s=before.decode();marker='  if (argc >= 2 && (!strcmp(argv[1], "track") || !strcmp(argv[1], "preview")))'
assert s.count(marker)==1
bench='''  if (argc == 3 && !strcmp(argv[1], "uartbench"))
    {
      char *end;
      long gap=strtol(argv[2],&end,10);
      if (!argv[2][0] || *end || gap<0 || gap>5000) return 1;
      for (unsigned int row=0;row<256;row++)
        {
          char payload[49];
          for (unsigned int j=0;j<48;j++) payload[j]='A'+(row+j)%26;
          payload[48]=0;
          printf("BENCH %03u %s\\n",row,payload);
          if(gap) usleep(gap);
        }
      usleep(10000);
      puts("BENCH DONE");
      return 0;
    }
'''
s=s.replace(marker,bench+marker);p.write_text(s)
(w/'bench-source.json').write_text(json.dumps({'target':str(p),'before':hashlib.sha256(before).hexdigest(),'after':hashlib.sha256(p.read_bytes()).hexdigest()},indent=2))
print('Installed bounded 256-row UART benchmark; no motor or camera calls')
