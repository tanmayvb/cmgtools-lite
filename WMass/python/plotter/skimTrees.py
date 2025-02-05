#!/usr/bin/env python
#from mcPlots import *
# python skimTrees.py wmass/wmass_e/mca-80X-wenu.txt wmass/wmass_e/skim_wenu.txt skims -P TREES_1LEP_80X_V3 --s2v -j 8 -F Friends "{P}/friends/tree_Friend_{cname}.root" -F Friends "{P}/friends/tree_FRFriend_{cname}.root"
from CMGTools.WMass.plotter.mcAnalysis import *

import array
import json
import ROOT
import re 

class CheckEventVetoList:
    _store={}
    def __init__(self,fname):
        self.loadFile(fname)
        print 'Initialized CheckEventVetoList from %s'%fname
        self.name = fname.strip().split('/')[-1]
    def loadFile(self,fname):
        with open(fname, 'r') as f:
            for line in f:
                if len(line.strip()) == 0 or line.strip()[0] == '#': continue
                run,lumi,evt = line.strip().split(':')
                self.addEvent(int(run),int(lumi),long(evt))
    def addEvent(self,run,lumi,evt):
        if (run,lumi) not in self._store:
            self._store[(run,lumi)]=array.array('L')
        self._store[(run,lumi)].append(evt)
    def filter(self,run,lumi,evt):
        mylist=self._store.get((run,lumi),None)
        return ((not mylist) or (long(evt) not in mylist))

class JSONSelector:
    jsonmap = {}
    def __init__(self,jsonfile):
        self.name = "jsonSelector"
        J = json.load(open(jsonfile, 'r'))
        for r,l in J.iteritems():
            self.jsonmap[long(r)] = l
        print "Loaded JSON %s with %d runs\n" % (jsonfile, len(self.jsonmap))
    def filter(self,run,lumi,evt):
        try:
            lumilist = self.jsonmap[run]
            for (start,end) in lumilist:
                if start <= lumi and lumi <= end:
                    return True
            return False
        except KeyError:
            return False

def _runIt(args):
        (tty,mysource,myoutpath,cut,mycut,options,selectors) = args
        mytree = tty.getTree()
        ntot  = mytree.GetEntries() 
        print "  Start  %-40s: %8d" % (tty.cname(), ntot)
        timer = ROOT.TStopwatch(); timer.Start()
        compression = options.compression
        if compression != "none":
            ROOT.gInterpreter.ProcessLine("#include <Compression.h>")
            (algo, level) = compression.split(":")
            compressionLevel = int(level)
            if   algo == "LZMA": compressionAlgo  = ROOT.ROOT.kLZMA
            elif algo == "ZLIB": compressionAlgo  = ROOT.ROOT.kZLIB
            else: raise RuntimeError("Unsupported compression %s" % algo)
            print "Using compression algo %s with level %d" % (algo,compressionLevel)
        else:
            compressionLevel = 0 
        # now we do
        os.system("mkdir -p "+myoutpath)
        os.system("cp -r %s/skimAnalyzerCount %s/" % (mysource,myoutpath))
        os.system("mkdir -p %s/%s" % (myoutpath,options.tree))
        histo = ROOT.gROOT.FindObject("Count")
        histoSumWeights = ROOT.gROOT.FindObject("SumGenWeights")
        if not options.oldstyle:
            fout = ROOT.TFile("%s/%s/tree.root" % (myoutpath,options.tree), "RECREATE", "", compressionLevel);
        else:
            fout = ROOT.TFile("%s/%s/%s_tree.root" % (myoutpath,options.tree,options.tree), "RECREATE", "", compressionLevel);
        if compressionLevel: fout.SetCompressionAlgorithm(compressionAlgo)
        mytree.Draw('>>elist',mycut)
        elist = ROOT.gDirectory.Get('elist')
        if len(options.vetoevents)>0:
            mytree.SetBranchStatus("*",0)
            mytree.SetBranchStatus("run",1)
            mytree.SetBranchStatus("lumi",1)
            mytree.SetBranchStatus("evt",1)
            mytree.SetBranchStatus("isData",1)
            elistveto = ROOT.TEventList("vetoevents","vetoevents")
            for ev in xrange(elist.GetN()):
                tev = elist.GetEntry(ev)
                mytree.GetEntry(tev)
                if not mytree.isData:
                    print "You don't want to filter by event number on MC, skipping for this sample"
                    break
                for selector in selectors:
                    if not selector.filter(mytree.run,mytree.lumi,mytree.evt):
                        print 'Selector %s rejected tree entry %d (%d among selected): %d:%d:%d'%(selector.name,tev,ev,mytree.run,mytree.lumi,mytree.evt)
                        elistveto.Enter(tev)
                        break
            mytree.SetBranchStatus("*",1)
            elist.Subtract(elistveto)
            print '%d events survived vetoes'%(elist.GetN(),)
        # drop and keep branches
        if options.dropall: mytree.SetBranchStatus("*",0)
        for drop in options.drop: mytree.SetBranchStatus(drop,0)
        for keep in options.keep: mytree.SetBranchStatus(keep,1)
        f2 = ROOT.TFile("%s/selection_eventlist.root"%myoutpath,"recreate")
        f2.cd()
        elist.Write()
        f2.Close()
        fout.cd()
        mytree.SetEventList(elist)
        out = mytree.CopyTree('1')
        npass = out.GetEntries()
        friends = out.GetListOfFriends() or []
        for tf in friends:
                out.RemoveFriend(tf.GetTree())
        fout.WriteTObject(out,options.tree if options.oldstyle else "tree")
        if histo: histo.Write()
        if histoSumWeights: histoSumWeights.Write()
        fout.Close(); timer.Stop()
        print "  Done   %-40s: %8d/%8d %8.1f min" % (tty.cname(), npass, ntot, timer.RealTime()/60.)


def addSkimTreesOptions(parser):
    parser.add_option("-D", "--drop",  dest="drop", type="string", default=[], action="append",  help="Branches to drop, as per TTree::SetBranchStatus") 
    parser.add_option("--dropall",     dest="dropall", default=False, action="store_true",  help="Drop all the branches (to keep only the selected ones with keep)") 
    parser.add_option("-K", "--keep",  dest="keep", type="string", default=[], action="append",  help="Branches to keep, as per TTree::SetBranchStatus") 
    parser.add_option("--oldstyle",    dest="oldstyle", default=False, action="store_true",  help="Oldstyle naming (e.g. file named as <analyzer>_tree.root)") 
    parser.add_option("--vetoevents",  dest="vetoevents", type="string", default=[], action="append",  help="File containing list of events to filter out")
    parser.add_option("--json",        dest="json", type="string", default=None, help="JSON file selecting events to keep")
    parser.add_option("--pretend",     dest="pretend", default=False, action="store_true",  help="Pretend to skim, don't actually do it") 
    parser.add_option("-z", "--compression",  dest="compression", type="string", default=("LZMA:9"), help="Compression: none, or (algo):(level) ")
    parser.add_option("-q", "--queue",   dest="queue",     type="string", default=None, help="Run jobs on lxbatch instead of locally");
    parser.add_option("-c", "--component", dest="component",   type="string", default=None, help="skim only this component");
    parser.add_option("--log", "--log-dir", dest="logdir", type="string", default=None, help="Directory of stdout and stderr");
    parser.add_option("-n", "--job-name", dest="jobName",   type="string", default="skimTrees", help="Name assigned to jobs");
    parser.add_option("--match-component", dest="matchComponent",   type="string", default="", help="Pass regular expression to match component names (particularly useful for friends when running in local");
    

if __name__ == "__main__":
    from optparse import OptionParser
    parser = OptionParser(usage="%prog [options] mc.txt cuts.txt outputDir")
    addSkimTreesOptions(parser)
    addMCAnalysisOptions(parser)
    (options, args) = parser.parse_args()
    options.weight = False
    options.final = True
    mca  = MCAnalysis(args[0],options)
    cut = CutsFile(args[1],options)
    outdir = args[2]

    print "Will write selected trees to "+outdir
    if not os.path.exists(outdir):
        os.system("mkdir -p "+outdir)

    selectors=[CheckEventVetoList(fname) for fname in options.vetoevents]
    if options.json: selectors.append(JSONSelector(options.json))

    if options.queue:

        ## first make the log directory to put all the condor files
        writelog = ""
        logdir   = ""
        if not options.logdir: 
            print 'ERROR: must give a log directory to make the condor files!\nexiting...'
            exit()
        else:
            logdir = options.logdir.rstrip("/")
            if not os.path.exists(logdir):
                os.system("mkdir -p "+logdir)

        ## constructing the command and arguments to run in condor submit file
        runner = "%s/src/CMGTools/WMass/python/postprocessing/lxbatch_runner.sh" % os.environ['CMSSW_BASE']
        cmdargs = [x for x in sys.argv[1:] if x not in ['-q',options.queue]]
        strargs=''
        for a in cmdargs: # join do not preserve " or '
            ## escaping not needed for condor if '{P}' in a or '*' in a: 
            ## escaping not needed for condor     a = '\''+a+'\''
            ## don't add --pretend option. --pretend just doesn't submit the condor file
            if '-p' in a or '--pretend' in a:
                continue
            strargs += ' '+a+' '
        for proc in mca.listProcesses():
            print 'Process %s' % proc
            condor_fn = options.logdir+'/condor_{p}.condor'.format(p=proc)
            condor_f = open(condor_fn,'w')
            condor_f.write('''Universe = vanilla
Executable = {runner}
use_x509userproxy = true
Log        = {ld}/{p}_$(ProcId).log
Output     = {ld}/{p}_$(ProcId).out
Error      = {ld}/{p}_$(ProcId).error
getenv      = True
request_memory = 4000
+MaxRuntime = 14400
+JobBatchName = "{name}"\n
'''.format(runner=runner,p=proc,ld=options.logdir,name=options.jobName))
            if os.environ['USER'] in ['mdunser', 'psilva']:
                condor_f.write('+AccountingGroup = "group_u_CMST3.all"\n')
            elif os.environ['USER'] in ['mciprian']:
                condor_f.write('+AccountingGroup = "group_u_CMS.CAF.ALCA"\n')
            condor_f.write('\n')

            for tty in mca._allData[proc]:
                print "\t component %-40s" % tty.cname()
                componentPost = ' --component {c} '.format(c=tty.cname())
                condor_f.write('\narguments = {d} {cmssw} python {self} {cmdargs} {comp}\n'.format(d=os.getcwd(),
                cmssw = os.environ['CMSSW_BASE'], self=sys.argv[0], cmdargs=strargs, comp=componentPost))
                condor_f.write('queue 1\n\n')
            condor_f.close()
            cmd = 'condor_submit {sf}'.format(sf=condor_fn)
            if options.pretend: 
                print cmd
            else:
                os.system(cmd)
        exit()

    tasks = []
    for proc in mca.listProcesses():
        if not options.component: print "Process %s" % proc
        for tty in mca._allData[proc]:
            if not options.component: print "\t component %-40s" % tty.cname()
            if options.component and tty.cname()!=options.component: continue
            if options.matchComponent: 
                if re.match(options.matchComponent,tty.cname()):
                    print "Component {n} matched filter".format(n=tty.cname())
                else:
                    print "Skipping {n}: doesn't match filter".format(n=tty.cname())
                    continue
            myoutpath = outdir+"/"+tty.cname()
            for path in options.path:
                mysource = path+"/"+tty.cname()
                if os.path.exists(mysource): break
            mycut = tty.adaptExpr(cut.allCuts(),cut=True)
            if options.doS2V: mycut  = scalarToVector(mycut)
            if options.pretend: continue
            tasks.append((tty,mysource,myoutpath,cut,mycut,options,selectors))

    print 'running {n} tasks'.format(n=len(tasks))
    if options.jobs == 0: 
        map(_runIt, tasks)
    else:
        from multiprocessing import Pool
        Pool(options.jobs).map(_runIt, tasks)
