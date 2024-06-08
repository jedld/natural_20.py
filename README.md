A Dungeons and Dragons game engine that can be used for AI related research

This project provides a complete Gymnasium compatible environment for performing
AI related research on the Dungeons and Dragons 5th edition RPGs.

Installation
============

```
pip install -r requirements.txt
```

Samples
=======

Please see the samples directory for samples.

Running Tests
=============

```python
python -m unittest discover tests
```

Run specific tests

```
python -m unittest tests.test_gym.TestGym.test_reset
python -m unittest tests.test_map.TestMap.test_line_of_sight
```