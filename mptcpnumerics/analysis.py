#!/usr/bin/python3
# attempt to do some monkey patching
# sympify can generate symbols from string
# http://docs.sympy.org/dev/modules/core.html?highlight=subs#sympy.core.basic.Basic.subs
# launch it with 
# $ mptcpnumerics topology.json compute_rto_constraints
# from mptcpanalyzer.command import Command

from enum import Enum, IntEnum
import sympy as sp
import argparse
import json
# import sympy as sy
import cmd
import sys
import logging
from collections import namedtuple
import sortedcontainers
import pulp as pu

log = logging.getLogger("mptcpnumerics")
log.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
#%(asctime)s - %(name)s - %
formatter = logging.Formatter('%(levelname)s - %(message)s')
handler.setFormatter(formatter)
log.addHandler(handler)
log.addHandler(logging.FileHandler("log",mode="w"))

"""
Hypotheses made in this simulator:
- subflows send full windows each time
- there is no data duplication, NEVER !
- windows are stable, they don't change because you reach the maximum size allowed
by rcv_window


TODO:
-use a framework to trace some variables (save into a csv for instance)
-support NR-sack
"""


from functools import wraps

def froze_it(cls):
    cls.__frozen = False

    def frozensetattr(self, key, value):
        if self.__frozen and not hasattr(self, key):
            print("Class {} is frozen. Cannot set {} = {}"
                  .format(cls.__name__, key, value))
        else:
            object.__setattr__(self, key, value)

    def init_decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            func(self, *args, **kwargs)
            self.__frozen = True
        return wrapper

    cls.__setattr__ = frozensetattr
    cls.__init__ = init_decorator(cls.__init__)

    return cls

def rto(rtt, svar):
    return rtt + 4* svar

class MpTcpCapabilities(Enum):
    """
    string value should be the one found in json's "capabilities" section
    """
    NRSACK = "Non renegotiable ack"
    DAckReplication =   "DAckReplication" 
    OpportunisticRetransmission = "Opportunistic retransmissions"

# TODO make it cleaner with Syn/Ack mentions etc..
class OptionSize(IntEnum):
    """
    Size in byte of MPTCP options
    """
    # 12 + 12 + 24
    Capable = 48
    # should be 12 + 16 + 24
    Join = 52
    FastClose = 12
    Fail = 12
    # 
    AddAddr4 = 10
    AddAddr6 = 22
    
    # 3 + n * 1 ?
    # RmAddr 

class DssAck(IntEnum):
    NoAck = 0
    SimpleAck = 4
    ExtendedAck = 8

class DssMapping(IntEnum):
    NoDss = 4
    Simple = 8
    Extended = 12



def dss_size(ack : DssAck, mapping : DssMapping, with_checksum: bool=False) -> int:
    """
    """
    size = 4
    size += ack.value
    size += mapping.value
    size += 2 if with_checksum else 0
    return size

# class MpTcpOverhead(Command):
#     """

#     """

#     def __init__(self):
#         pass

#     def _dss_size(ack : DssAck, mapping : DssMapping, with_checksum: bool=False) -> int:
#         """
#         """
#         size = 4
#         size += ack.value
#         size += mapping.value
#         size += 2 if checksum else 0
#         return size

#     def _overhead_const (total_nb_of_subflows : int):
#         """
#         Returns constant overhead for a connection

#         Mp_CAPABLE + MP_DSSfinal + sum of MP_JOIN
#         """
#         oh_mpc, oh_finaldss, oh_mpjoin, nb_subflows = sp.symbols("OH_{MP_CAPABLE} OH_{Final dss} OH_{MP_JOIN} n")
#         # TODO test en remplacant les symboles
#         # TODO plot l'overhead d'une connexion
#         constant_oh = oh_mpc + oh_finaldss + oh_mpjoin * nb_subflows
#         # look at simpify
#         # .subs(
#         # todo provide a dict
#         constant_oh.evalf()
#         return OptionSize.Capable.value + total_nb_of_subflows * OptionSize.Join.value

#     def do(self, data):
#         parser = argparse.ArgumentParser(description="Plot overhead")
#         parser.add_argument("topologie", action="store", help="File to load topology from")
#         args = parser.parse_args(shlex.split(args))
#         # print("hello world")
#         # json.load()
# # TODO this should be a plot rather than a command
#         print("topology=", args.topology ) 
#         with open(args.topology) as f:
#             j = json.load(f)
#             print("Number of subflows=%d" % len(j["subflows"]))
#             for s in j["subflows"]:
#                 print("MSS=%d" % s["mss"])
# # TODO sy.add varying overhead
#                 # sy.add 
#             print("toto")

#     def help(self):
#         """
#         """
#         print("Allow to generate stats")

#     def complete(self, text, line, begidx, endidx):
#         """
#         """

# # name/value
class HOLTypes(Enum):
    """
    names inspired from  SCTP paper

    """
    GapedAck = "GapAck-Induced Sender Buffer Blocking (GSB)"
    RcvBufferBlocking = "rcv buffer RcvBufferBlocking"
    ReceiverWindowBlocking = "Window-Induced Receiver Buffer Blocking"
    ReceiverReorderingBlocking = "Reordering-Induced Receiver Buffer Blocking"
    # Transmission-Induced Sender Buffer Blocking (TSB)



"""
"""
# Event = collections.namedtuple('Event', ['time', 'subflow', 'direction', 'dsn', 'size', 'blocks'])

class Event:
    """
    Describe an event in simulator. 
    As it is 
    """

    def __init__(self, sf_id, direction, **args):
        """
        special a list of optional features listed in EventFeature
        Either set 'delay' (respective) or 'time' (absolute scheduled time)
        direction => destination of the packet TODO rename
        """
        self.direction = direction
        self.time = None
        self.subflow_id = sf_id
        self.delay = None

        self.special = []

    def __str__(self):
        return "Scheduled at {s.time} dest={dest}".format(
                s=self,
                dest="sender" if self.direction == Direction.Sender else "Receiver",
                )


class SenderEvent(Event):
    def __init__(self, sf_id ):
        super().__init__(sf_id, Direction.Receiver)
        self.dsn = None
        self.size = None

    def __str__(self):
        res = super().__str__()
        res += " dsn={s.dsn} size={s.size}".format(
                s=self)
        return res

# @froze_it
class ReceiverEvent(Event):

    def __init__(self, sf_id):
        super().__init__(sf_id, 
#dack, rcv_wnd,
Direction.Sender)

        self.dack = None
        self.rcv_wnd = None
        
        # in case Sack is used
        self.blocks = []

    def __str__(self):
        res = super().__str__()
        res += " dack={s.dack} rcv_wnd={s.rcv_wnd}".format(s=self)
        return res


class MpTcpSubflow:
    # may change
    # should be sympy symbols ?
    # fixed values
    def __init__(self, upper_bound,  name,  mss, fowd, bowd, loss, var, cwnd=None, **extra):
        """
        In this simulator, the cwnd is considered as constant, at its maximum.
        Hence the value given here will remain
        """
        # self.sender = sender
            # loaded_cwnd = sf_dict.get("cwnd", self.rcv_wnd)
        # FREE
        # upper_bound = min( upper_bound, cwnd ) if cwnd else upper_bound
        # cwnd = pu.LpVariable (name, 0, upper_bound)
        # self.cwnd = cwnd
        self.cwnd = sp.Symbol("cwnd_{%s}" % name, positive=True)
        sp.refine(self.cwnd, sp.Q.positive(upper_bound - self.cwnd))

        print("%r"% self.cwnd)

        self.name = name

        # self.una = 0
        # TODO rename to 'inflight'
        self.inflight = False
        # unused for now
        self.svar = 10
        self.mss = mss

        # forward and Backward one way delays
        self.fowd = fowd
        self.bowd = bowd
        self.loss_rate = loss

        # print("TODO")
        # print(extra)

    # def __repr__(self):
    def __str__(self):
        """
        """
        return "Id={s.name} Rtt={s.fowd}+{s.bowd} inflight={s.outstanding}".format(
                s=self
                )

    def busy(self) -> bool:
        """
        true if a window of packet is in flight
        """
        return self.inflight


    def rto(self):
        """
        Retransmit Timeout
        """
        return rto (self.rtt, self.svar)

    def rtt(self):
        """
        Returns constant Round Trip Time
        """
        return self.fowd + self.bowd

    # def right_edge(self):
    #     return self.una + self.cwnd

    def increase_window(self):
        """
        Do nothing for now or uncoupled
        """
        # self.cwnd += MSS
        pass 

    def ack_window(self):
        """

        """
        # self.una += self.cwnd
        assert self.busy() == True
        self.increase_window()
        self.inflight = False


    def generate_pkt(self, dsn, ):
        """
        Generates a packet with a full cwnd
        """
        assert self.inflight == False

        e = SenderEvent(self.name)
        e.delay = self.fowd
        # e.subflow_id = self.name
        e.dsn  = dsn
        e.size = self.cwnd

        print("packet size %r"% e.size)

        # a
        # self.una = dsn
        self.inflight = True
        return e



class MpTcpSender:
    """
    By definition of the simulator, a cwnd is either fully outstanding or empty
    """
    # subflow congestion windows
    # need to have dsn, cwnd, outstanding ?

    # TODO maintain statistics about the events and categorize them by HOLTypes
    def __init__(self, config):
        """
        self.rcv_wnd is a 
        self.subflows is a dict( subflow_name, MpTcpSubflow)
        """
        self.snd_buf_max = config["sender"]["snd_buffer"]
        # self.left = 0
        # self.wnd = self.
        # self.subflows = config["subflows"]

        self.snd_next = 0    # left edge of the window/dsn (rename to snd_una ?)
        self.snd_una = 0
        self.rcv_wnd = config["receiver"]["rcv_buffer"]
        
        self.subflows = {}
        for sf_dict in config["subflows"]:
            print("test", sf_dict)
            # self.cwnd = sp.IndexedBase("cwnd_{name}")
            upper_bound = min(self.snd_buf_max, self.rcv_wnd)
            # cwnd has to be <= min(rcv_buf, snd_buff) TODO add
            
            subflow = MpTcpSubflow( upper_bound=upper_bound, **sf_dict)
            self.subflows.update( {sf_dict["name"]: subflow} )
            # sort them by subflow
            # sp.Symbol()
        print(self.subflows)
        

    def __setattr__(self, name, value):
        if name == "snd_next":
            log.debug("UPDATE snd_next to %s", value)
        self.__dict__[name] = value

    # rename to inflight
    def inflight(self):
        inflight = 0
        for sf_id, sf in self.subflows.items():
            if sf.inflight == True:
                inflight += sf.cwnd
        # sum(filter(lambda x: x.cwnd if x.inflight), self.subflows)
        return inflight

    def available_window(self):
        # min(self.snd_buf_max, self.rcv_wnd)
        return self.rcv_wnd - self.inflight()

    def snd_nxt(self):
        """
        returns snd_next
        """
        # max(iterable, *[, key, default])
        # max(arg1, arg2, *args[, key])
        return self.snd_next
        # return max(self.subflows, "dsn", 0)

    def send(self, sf_id):
        """
        rely on MpTcpSubflow:generate_pkt function
        """
        # e = SenderEvent()
        # sf = self.subflows[sf_id]
        # e.time = current_time + sf["f"]
        # e.subflow_id = sf_id
        assert self.subflows[sf_id].busy() == False


        dsn = self.snd_nxt()
        pkt = self.subflows[sf_id].generate_pkt(dsn)
        self.snd_next += pkt.size 
        return pkt

    #     # a
    #     self.snd_next += self.subflows[sf_id]["cwnd"]

    #     e.size = self.subflows[sf_id]["cwnd"]
    #     return e

    def __str__(self):
        res = "SND.MAX={snd_max} Nxt={nxt} UNA={una}".format(
                snd_max=self.snd_buf_max,
                nxt = self.snd_next,
                una=self.snd_una,
                )
        return res

    def __repr__(self):
        #:
        res = self.__str__()
        res += "Subflows:\n"
        for sf in self.subflows:
            # print ( " == Subflows ==")
            res += "- id={id} cwnd={cwnd}".format(
                    cwnd=sf["cwnd"],
                    id=sf["id"],
                    )

    def recv(self, p):
        """
        Process acks
        pass a bool or function to choose how to increase cwnd ?
        """
        log.debug("Sender received packet %s" % p)



        print ("comparing %s (dack) > %s (una) => result = %s " % (p.dack, self.snd_una, p.dack > self.snd_una ))

#   // Test for conditions that allow updating of the window
#   // 1) segment contains new data (advancing the right edge of the receive
#   // buffer),
#   // 2) segment does not contain new data but the segment acks new data
#   // (highest sequence number acked advances), or
#   // 3) the advertised window is larger than the current send window
#         self.snd_una= max(self.snd_una, p.dack)
        # TODO should update 
        print( p.dack > self.snd_una )
        if p.dack > self.snd_una:
            self.rcv_wnd = p.rcv_wnd
        elif p.rcv_wnd > self.rcv_wnd:
            self.rcv_wnd = p.rcv_wnd
        else:
            log.warn("Not advancing rcv_wnd")

        # TODO we should not ack if in disorder ?
        self.subflows[p.subflow_id].ack_window ()

        # for name,sf in self.subflows.items():
        #     if p.dack >= self.left_edge():
        #         sf.ack_window()

        # TODO regenerate packets

            # now loo
        # cwnd
        return

class Direction(Enum):
    Receiver = 0
    Sender = 1


OutOfOrderBlock = namedtuple('OutOfOrderBlock', ['dsn', 'size'])
Constraint = namedtuple('Constraint', ['time', 'size', 'wnd'])
# print("%r", OutOfOrderBlock)
# b = OutOfOrderBlock(40,30)
# print(b.dsn)
# system.exit(1)

class MpTcpReceiver:
    """
    Max recv window is set from json file
    """

    def __init__(self, capabilities, config):
        """
        """
        self.config = config
        # self.rcv_wnd_max = max_rcv_wnd
        # self.j["receiver"]["rcv_buffer"]
        # rcv_left, rcv_wnd, rcv_max_wnd = sp.symbols("dsn_{rcv} w_{rcv} w^{max}_{rcv}")
        self.subflows = {}
        #self.rcv_wnd_max = sp.Symbol("W^{receiver}_{MAX}")
        self.rcv_wnd_max = config["receiver"]["rcv_buffer"]
        self.wnd = self.rcv_wnd_max
        self.rcv_next = 0
        # a list of tuples (headSeq, endSeq)
        self.out_of_order = []
        for sf in config["subflows"]:
            self.subflows.update( {sf["name"]: sf})
            # self.subflows.update( {sf["id"]: sf})

    # def inflight(self):
    #     raise Exception("TODO")
    #     # return map(self.subflows)
    #     pass
    def __setattr__(self, name, value):
        if name == "rcv_next":
            log.debug("Changing rcv_next to %s", value)
        self.__dict__[name] = value

    # rename to advertised_window()
    def window_to_advertise(self):
        ooo = 0
        for block in self.out_of_order:
            print("BLOCK=%r", block)
            ooo += block.size

        return self.rcv_wnd_max - ooo 
    #- inflight

    def left_edge(self):
        """
        what sequence number is expected next
        """
        return self.rcv_next

    def right_edge(self):
        """
        Max seq number it can receive
        """
        return self.left_edge() + self.rcv_wnd_max

    def in_range(self, dsn, size):
        return dsn >= self.left_edge() and dsn + size < self.right_edge()

    def add_packet(self, p):
        pass

    def generate_ack(self, sf_id):
        """
        """
        # super().gen_packet(direction=)
        log.debug("Generating ack for sf_id=%s" % sf_id)
        # TODO
        # self.subflows[sf_id].ack_window()
        e = ReceiverEvent(sf_id)
        e.delay = self.subflows[sf_id]["bowd"]
        e.dack = self.rcv_next
        e.rcv_wnd = self.window_to_advertise()
        return e


    def update_out_of_order(self):
        """
        tcp-rx-buffer.cc:Add
        removes packets from out of order buffer when they get in order
        """
        # print(self.out_of_order)
        temp = sorted(self.out_of_order, key=lambda x : x[0])
        new_list = []
        # todo use size instead
        for block in temp:
            print("rcv_next={nxt} Block={block}".format(
                nxt=self.rcv_next,
                block=block,
                )
            )
            if self.rcv_next == block.dsn:
                self.rcv_next = block.dsn + block.size
                # log.debug ("updated ")
            else:
                new_list.append(block)

        # swap old list with new one
        self.out_of_order = new_list


    def recv(self, p):
        """
        @p packet
        return a tuple of packet
        """
        # assume it's always in range else we can get an error like 
        # TypeError: cannot determine truth value of Relational
        # if not self.in_range(p.dsn, p.size):
        #     raise Exception("Error")


        log.debug("Receiver received packet %s" % p)
        packets = []
        
        headSeq = p.dsn
        tailSeq = p.dsn + p.size

        # if tailSeq > self.right_edge():
        #     tailSeq = self.right_edge()    
        #     log.error ("packet exceeds what should be received")
        print("headSeq=%r vs %s"%( headSeq, (self.rcv_next)))
        # with sympy, I can do 
        # if sp.solve(headSeq < self.rcv_next) is True:
        # # if headSeq < self.rcv_next:
        #     headSeq = self.rcv_next

        # if headSeq > self.rcv_next:
            # if programmed correctly all packets should be within bounds
            # if headSeq > self.right_edge():
            #     raise Exception("packet out of bounds")
            # assert headSeq < tailSeq
            # self.
        block = OutOfOrderBlock(headSeq, p.size)
        self.out_of_order.append ( block )
        # else:
        #     self.rcv_next = tailSeq
            # print("Set rcv_next to ", self.rcv_next)

        self.update_out_of_order()

        print("TODO: check against out of order list")


        if MpTcpCapabilities.DAckReplication in self.config["receiver"]["capabilities"]:
            # for sf in self.subflows:
            #     self.generate_ack()
            #     e.subflow = p.subflow
            #     packets.append(e)
            pass
        else:
            e = self.generate_ack(p.subflow_id)
            packets.append(e)

        # print(packets)
        return packets

class Simulator:
    """
    You should start feeding some packets/events (equivalent in this simulator)
    with the "add" method.
    You may also choose a time limit at which to "stop()" the simulator or alternatively wait
    for the simulation to run out of events.

    Once the scenario, is correctly setup, call "run" and let the magic happens !

    """
        # should be ordered according to time
        # events = []
    def __init__(self, sender : MpTcpSender, receiver : MpTcpReceiver):
        """
        current_time is set to the time of the current event
        :param sender ok
        """
        self.sender = sender
        self.receiver = receiver
        
        # http://www.grantjenks.com/docs/sortedcontainers/sortedlistwithkey.html#id1
        self.events = sortedcontainers.SortedListWithKey(key=lambda x: x.time)
        self.time_limit = None
        self.current_time = 0

        # list of constraints that will represent the problem when simulation ends
        self.constraints =[]
        self.throughput 

    def add(self, p):
        """
        Insert an event
        """
        if p.delay is not None:
            p.time = self.current_time + p.delay

        assert p.time >= self.current_time
        log.info("Adding event %s " % p)

        # VERY IMPORTANT
        if p.direction == Receiver:

            # todo sauvegarder le temps, dsn, size necessaire
            # self.constraints.append()
        self.events.add(p)
        print(len(self.events), " total events")

    def solve_constraints(self, backend="pulp"):
        """
        Converts from sympy to pulp
        https://github.com/uqfoundation/mystic
        http://www.pyomo.org/
        https://github.com/coin-or/pulp
        """

        #create a binary variable to state that a table setting is used
        pb = pulp.LpProblem("Subflow congestion windows repartition", pu.LpMinimize)

        # TODO replace sympy variables in constraints with pulp variables.
        # expr.subs() ; can be used with a dict
        for constraint in self.constraints:
            to_substitute = {}
            for sym in constraint.free_symbols():
                # ...
                translation = already_translated.get(sym, None)
                if translation is None:
                    # TODO generate an LpVariable
                    # generate depending on sym.name
                    # ...
                    translation = pu.LpVariable(
                # pu.LpConstraint
                to_substitute.update( (sym, translation) )

        # .atoms(Symbol)
        # .free_symbols
        # symbol.name
# symbols('a0:%d'%numEquations)
# numbered_symbols
        # http://docs.sympy.org/0.7.3/tutorial/basic_operations.html#substitution
        pu.LpVariable.dicts('table', 
                                possible_tables, 
                                lowBound = 0,
                                upBound = 1,
                                cat = pu.LpInteger)
        
        # TODO il faut ajouter la fct objectif
        pb += 
        
        
        
        # https://pythonhosted.org/PuLP/pulp.html
        # The problem data is written to an .lp file
        pb.writeLP("constraints.lp")



        pb.solve()
        # The status of the solution is printed to the screen
        print("Status:", LpStatus[prob.status])
        # Each of the variables is printed with it's resolved optimum value
        for v in prob.variables():
            print(v.name, "=", v.varValue)
        # The optimised objective function value is printed to the screen
        print("Total Cost of Ingredients per can = ", value(prob.objective))


    def add_constraint(self, size, rcv_wnd):
        c = Constraint(self.current_time, size, rcv_wnd)
        self.constraints.append(c)

    def run(self):
        """
        Starts running the simulation
        """

        log.info("Starting simulation,  %d queued events " % len(self.events))
        for e in self.events:

            self.current_time = e.time
            if self.time_limit and self.current_time > self.time_limit:
                print("Duration of simulation finished ! Break out of the loop")
                break

            log.debug("%d: running event %r" % (self.current_time, e))
            # events emitted by host
            pkts = []
            if e.direction == Direction.Receiver:
                pkts = self.receiver.recv(e)
            elif e.direction == Direction.Sender:
                pkts = self.sender.recv(e)
                map(lambda x: self.add_constraint(x.size, self.sender.available_window()), pkts)
            else:
                raise Exception("wrong direction")
            
            print(pkts)
            if pkts:
                for p in pkts:
                    self.add(p)
            else:
                log.error("No pkt sent by either receiver or sender")

        # constraints = []
        self.sender.constraints()
        return constraints

    def stop(self, stop_time):
        """
        """
        log.info("Setting stop_time to %d" % stop_time)
        self.time_lmit = stop_time




class MpTcpNumerics(cmd.Cmd):
    """
    """

    def __init__(self, stdin=sys.stdin): 
        """
        stdin 
        """
        self.prompt = "Rdy>"
        # stdin ?
        super().__init__(completekey='tab', stdin=stdin)

    def do_load(self, filename):
        with open(filename) as f:
            self.j = json.load(f)
            print(self.j["subflows"])
            total = sum(map(lambda x: x["cwnd"], self.j["subflows"]))
            print("Total of Cwnd=", total)
            # self.sender = 
            # self.subflows = map( lambda x: MpTcpSubflow(), self.j["subflows"])
            print("toto")

    def do_print(self, args):

        print("Number of subflows=%d" % len(self.j["subflows"]))
        for idx,s in enumerate(self.j["subflows"]):
            print(s)
            msg = "Sf {id} MSS={mss} RTO={rto} rtt={rtt}={fowd}+{bowd}".format(
                # % (idx, s["mss"], rto(s["f"]+s["b"], s['var']))
                id=idx,
                rto=rto(s["fowd"] + s["bowd"], s["var"]),
                mss=s["mss"],
                rtt=s["fowd"] + s["bowd"],
                fowd=s["fowd"],
                bowd=s["bowd"],
                )
            print(msg)
            # TODO sy.add varying overhead
            # sy.add 

    def do_cycle(self, args):
        return self._compute_cycle()

    def _compute_cycle(self):
        """
        returns (approximate lcm of all subflows), (perfect lcm ?)
        """

        rtts = list(map(lambda x: x["fowd"] + x["bowd"], self.j["subflows"]))
        lcm = sp.ilcm(*rtts)

        # lcm = rtts.pop()
        # print(lcm)
        # # lcm = last["f"] + last["b"]
        # for rtt in rtts:
        #     lcm = sp.lcm(rtt, lcm)
        return lcm
        # sp.lcm(rtt)

    def do_compute_constraints(self, args):
        """
        """
        duration = self._compute_cycle()
        self._compute_constraints(duration)

    def do_compute_rto_constraints(self, args):
        """
        """
        parser = argparse.ArgumentParser(description="hello world")
        parser.add_argument('subflow', metavar="SUBFLOW ID", choices=list(map(lambda x: x["name"], self.j["subflows"])) , 
                help="Choose for which subflow to compute RTO requirements")
        for subflow in self.j:
            self.per_subflow_rto_constraints(subflow)

    def do_subflow_rto_constraints(self, args):
        # use args as the name of the subflow ids
        self.per_subflow_rto_constraints()

    def per_subflow_rto_constraints(self, fainting_subflow):
        """
        fainting_subflow : subflow which is gonna lose its packets
        """
        # TODO should be 
        capabilities = self.j["capabilities"]
        receiver = MpTcpReceiver(capabilities, self.j)
        sender = MpTcpSender(self.j,) 

        sim = Simulator(sender, receiver)

        # we start sending a full window over each path
        # sort them depending on fowd
        # subflows = sorted(self.j["subflows"] , key=lambda x: x["fowd"] , reverse=True)

        log.info("Initial send")
        subflows = sender.subflows.values()
        subflows = sorted(subflows, key=lambda x: x.fowd, reverse=True)

        # that can't work, since we don't know the real values
        # while sender.available_window():
            
        for sf in subflows:
                
            # ca genere des contraintes
            # pkt = sf.generate_pkt(0, sender.snd_next)
            pkt = sender.send(sf.name)
            if sf == fainting_subflow:
                log.debug("Mimicking an RTO => Needs to drop this pkt")
                sim.stop ( fainting_subflow.rto() )
                continue
            sim.add(pkt)
            
        return sim.run()


    def _compute_constraints(self, duration):
        """
        Options and buffer size are loaded from topologies
        Compute constraints during `duration`

        Create an alternative scenario where one flow has an rto

        Return a list of constraints/stats
        """

        print("Cycle duration ", duration)
        # sp.symbols("
        # out of order queue
        rcv_ooo = []

        capabilities = self.j["capabilities"]

        # creation of the two hosts
        receiver = MpTcpReceiver(capabilities, self.j)
        sender = MpTcpSender(self.j,) 

        sim = Simulator(sender, receiver)

        # we start sending a full window over each path
            # sort them depending on fowd
        subflows = sorted(self.j["subflows"] , key=lambda x: x["fowd"] , reverse=True)

        # global current_time
        # current_time = 0

        log.info("Initial send")
        while sender.available_window():
            for sf in subflows:
            # TODO check how to insert in 
                
                pkt = sf.generate_pkt(0, sender.snd_next)
                self.events.add(pkt)




        print("loop finished")
        return

    def do_export_constraints_to_cplex():
        """
        Once constraints are computed, one can 
        """
        pass

    def do_q(self, args):
        """
        Quit/exit program
        """
        return True

    def do_plot_overhead(self, args):
        """
        total_bytes is the x axis,
        y is overhead
        oh_mpc
        IN
        = 12 + 16 + 24 = 52 OH_MPC= 12 + 12 + 24 
        OH_MPJOIN= 12 + 16 + 24 = 52
        To compute the variable part we can envisage 2 approache
        """
        print("Attempt to plot overhead via sympy")
        # this should a valid sympy expression

        real_nb_subflows = len(self.j["subflows"])
        print("There are %d subflows" % real_nb_subflows)

        oh_mpc, oh_finaldss, oh_mpjoin, nb_subflows = sp.symbols("OH_{MP_CAPABLE} OH_{DFIN} OH_{MP_JOIN} N")

# cls=Idx
        i = sp.Symbol('i', integer=True)
        total_bytes = sp.Symbol('bytes', )
        # nb_subflows = sp.Symbol('N', integer=True)
        # mss = sp.IndexedBase('MSS', i )
        sf_mss = sp.IndexedBase('MSS')
        sf_dss_coverage = sp.IndexedBase('DSS')
        # sf_ratio = sp.IndexedBase('ratio')
        sf_bytes = sp.IndexedBase('bytes')

        # this is per subflows
        n_dack, n_dss  = sp.symbols("S_{dack} S_{dss}") 

        def _const_overhead(): 
            return oh_mpc + oh_finaldss + oh_mpjoin * nb_subflows

        def _variable_overhead():
            """
            this is per subflow
            """

            # nb_of_packets = total_bytes/mss

            variable_oh =  sp.Sum( (n_dack * sf_bytes[i])/sf_mss[i] + n_dss * sf_bytes[i]/sf_dss_coverage[i], (i,1,nb_subflows))
            return variable_oh

        # sum of variable overhead
        variable_oh = _variable_overhead()
        # print("MPC size=", OptionSize.Capable.value,)
        # sympy_expr.free_symbols returns all unknown variables
        d = {
                oh_mpc: OptionSize.Capable.value,
                oh_mpjoin: OptionSize.Join.value,
                oh_finaldss: DssAck.SimpleAck.value,
                nb_subflows: real_nb_subflows,
                # n_dack: nb_of_packets, # we send an ack for every packet
                n_dack: DssAck.SimpleAck.value,
                n_dss:  dss_size(DssAck.NoAck, DssMapping.Simple),
        }


        # TODO substiture indexed values
# http://stackoverflow.com/questions/26402387/sympy-summation-with-indexed-variable 
        # -- START -- 
        # f = lambda x: Subs(
        #         s.doit(), 
        #         [s.function.subs(s.variables[0], j) for j in range(s.limits[0][1], s.limits[0][2] + 1)], 
        #         x
        #         ).doit()
        # f((30,10,2))
        # # -- END --


        # then we substitute what we can (subs accept an iterable, dict/list)
        # subs returns a new expression
        
        total_oh = _const_overhead() + variable_oh 
        # print("latex version=", sp.latex(total_oh))
        # numeric_oh = total_oh.subs(d)

        print("latex version=", sp.latex(variable_oh))
        def _test_matt(s, ratios):
            # print("%r %r" % (s.limits, s.limits[0][0] ) )
            # print(self.j["subflows"][1])
            # print(s.variables[0])
            # print(s.limits[0][0].subs(i, 4) )
            # for z in range(s.limits[0][1], s.limits[0][2] ): 
            for z in range(1,real_nb_subflows+1):
                # print(z)

                print("After substitution s=", s)
                s = s.subs( {
                    sf_mss[z]: self.j["subflows"][z-1]["mss"],
                    # sf_bytes[z]: total_bytes, # self.j["subflows"][i],
                    sf_bytes[z]: ratios[z-1] * total_bytes, # self.j["subflows"][i],
                    sf_dss_coverage[z]: 1500
                }).doit()

            return s.subs({

                n_dack: DssAck.SimpleAck.value,
                n_dss:  dss_size(DssAck.NoAck, DssMapping.Simple),
                })
        variable_oh = variable_oh.subs(nb_subflows,real_nb_subflows)
        test = sp.Rational(1,2)
        var_oh_numeric = _test_matt(variable_oh.doit(), [test,test])


        # numeric_oh.subs(
        print("After substitution=", sp.latex(var_oh_numeric))
        print("After substitution=", sp.latex(var_oh_numeric))
        # print("After substitution=", sp.latex(numeric_oh))
        # print("After substitution=", sp.latex(numeric_oh.doit()))

        # there should be only total_bytes free
        sp.plotting.plot(var_oh_numeric)


def run():
    parser = argparse.ArgumentParser(
        description='Generate MPTCP stats & plots'
    )

    #  todo make it optional
    parser.add_argument("input_file", action="store",
            help="Either a pcap or a csv file (in good format)."
            "When a pcap is passed, mptcpanalyzer will look for a its cached csv."
            "If it can't find one (or with the flag --regen), it will generate a "
            "csv from the pcap with the external tshark program."
            )
    parser.add_argument("--debug", "-d", action="store_true",
            help="To output debug information")
    parser.add_argument("--batch", "-b", action="store", type=argparse.FileType('r'),
            default=sys.stdin,
            help="Accepts a filename as argument from which commands will be loaded."
            "Commands follow the same syntax as in the interpreter"
            )
    # parser.add_argument("--command", "-c", action="store", type=str, nargs="*", help="Accepts a filename as argument from which commands will be loaded")

    args, unknown_args = parser.parse_known_args(sys.argv[1:])
    analyzer = MpTcpNumerics()
    analyzer.do_load(args.input_file)
    if unknown_args:
        log.info("One-shot command: %s" % unknown_args)
        analyzer.onecmd(' '.join(unknown_args))
    else:
        log.info("Interactive mode")
        analyzer.cmdloop()

if __name__ == '__main__':
    run()