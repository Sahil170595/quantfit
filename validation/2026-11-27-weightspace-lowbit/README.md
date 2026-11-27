# Grouped delta wheel validation

On Windows x64 CPU, install the Quantfit 0.78.0 wheel with NumPy 2.5.1 and SafeTensors 0.8.0. Run `python -I tools/ci_weightspace_lowbit.py` outside the import path of the checkout. The aggregate record compares both physical code streams, group scales, file sizes and decoded coefficients against a scalar implementation. The fixtures cover every supported signed code, an odd final length and an all-zero group. These synthetic results measure codec arithmetic and serialized sizes. Model quality and real-checkpoint compression require separate evaluation.
