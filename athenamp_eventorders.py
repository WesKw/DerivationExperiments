import sys

# sys.argv[0] => program name
# sys.argv[1] => number of processes
# sys.argv[2] => number of events per process

nrepeats=int(int(sys.argv[2])/10)
# with open("athenamp_eventorders.txt."+sys.argv[0],"w") as f:
with open("athenamp_eventorders.txt.Derivation", "w") as f:
    for i in range(0,int(sys.argv[1])):
        if nrepeats==0:
            print(str(i)+':'+','.join([str(x) for x in range(0,int(sys.argv[2]))]),file=f)
        else:
            print(str(i)+':'+','.join([str(x) for x in range(0,10)]*nrepeats),file=f)
