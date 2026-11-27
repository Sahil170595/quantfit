# Arithmetic task-vector acceptance

On Windows x64, Python 3.14.7, NumPy 2.5.1 and SafeTensors 0.8.0, install the 0.77.0 candidate wheel and run `python -I tools/ci_weightspace_vectors.py`. The program checks four scales against independent Python scalar arithmetic and confirms that the integer counter survives. [Aggregate results](functional.json)

The fixture exercises numerical update semantics. It does not establish behavior retention or gains on downstream tasks.
