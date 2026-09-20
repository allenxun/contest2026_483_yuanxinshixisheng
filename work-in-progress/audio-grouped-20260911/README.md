# RXDR grouped capture candidate

This candidate follows the board-observed eight-read RXDR rotation: four FIFO
banks and two read positions per bank. It maps all four receive paths to SDI0,
waits for one entry in every bank, consumes two eight-word slot groups for each
16 kHz stereo frame, and reports disagreement among the four copies. The first
group becomes the left slot and the second becomes the right slot.

Host simulation is necessary software evidence only. Hardware acceptance must
show 16 kHz duration, bounded stop/cleanup, nonzero speech PCM, and a low copy
mismatch count before this path can feed ASR. The candidate does not enable DMA,
write eMMC, or suppress arbitrary zero samples.

Run:

```powershell
python .\work-in-progress\audio-grouped-20260911\run_tests.py
```
