# scheduler
perso


format de fichiers:


rcv_buffer/snd_buffer are in KB.
fowd/bowd are in ms
loss is in % .
cwnd is the size of the subflow congestion window in (kbytes)
(cwnd might disappear and loss is not used yet)


{
	"name": "test00",
	"sender": {
		"snd_buffer": 40,
		"capabilities": ["NR-SACK"]
	},
	"receiver": {
		"rcv_buffer": 40,
		"capabilities": ["NR-SACK"]
	},

	"capabilities": ["NR-SACK"],
	"subflows": [
		{
			"name": "sffb",
			"cwnd": 0.8,
			"mss": 1500,
			"var": 10,
			"fowd": 50,
			"bowd": 10,
			"loss": 0.05
		},
		{
			"name": "ffsb",
			"cwnd": 0.1,
			"mss": 1500,
			"var": 10,
			"fowd": 10,
			"bowd": 50,
			"loss": 0.05
		}
	]
}
