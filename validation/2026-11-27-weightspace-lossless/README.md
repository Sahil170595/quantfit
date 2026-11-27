# Lossless CPU checkpoint delta

On Windows x64 with Python 3.14.7, NumPy 2.5.1 and SafeTensors 0.8.0, build and install the 0.76.0 candidate wheel. Run `python -I tools/ci_weightspace.py` with that interpreter. It fits two small linear classifiers, encodes the target through the installed Python API, decodes through the installed console entry point, then independently loads and scores the recovered weights. [Aggregate observations](functional.json)

Four of four held-out predictions and both tensors matched exactly. The example establishes reconstruction for this fixture. It does not measure compression effectiveness on production checkpoints, accelerator performance or transfer to a smaller model.
