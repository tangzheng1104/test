# -*- coding: utf-8 -*-
# mcsas_test.py

from __future__ import print_function # python3 print()

import os.path
import pickle
import numpy

from McSAS import McSAS

TOL = 1e-16 # usual eps value for 64bit float
FN_TEST_DATA = "test_data.pydat"
FN_EXPECTED_DATA = "test_data_result.pydat"

def isEqualFloat(a, b, tol = TOL):
    """Return TRUE if both float arrays can be considered as equal.
       *tol* Tolerance in relative mean difference
       Supposed to be symmetrical."""
    # equal = numpy.allclose(a, b, rtol = 0.0, atol = TOL)

    # one could also think about using the relative mean difference:
    # http://stackoverflow.com/a/4029392
    diff = (abs(a-b) / (abs(a)+abs(b)) / 2.)
    equal = numpy.all(diff < tol)

    print("max difference: {0} ({1})".format(numpy.max(diff), tol))
    return equal

def getTestData(filename):
    # read test data file
    with open(filename) as fd:
        qie = pickle.load(fd)

    # separate input data vectors
    return (qie[0,:], qie[1,:], qie[2,:])

def getExpectedData(filename):
    exp = None
    if os.path.exists(filename):
        print("Reading expected test results from file ... ")
        with open(filename) as fd:
            exp = pickle.load(fd)
        print("done.")
    return exp

def storeResultData(filename, result):
    print("Storing test results to file ... ")
    assert not os.path.exists(filename),\
        "Target file for test results exists already! "\
        "Not overwriting, remove first."
    with open(filename, 'w') as fd:
        pickle.dump(result, fd)
    print("done.")

def getSettings(testfn, expectedfn):
    """Test settings for mcsas routine.
    Using number of repetitions and contributions
    from expected test data to improve comparability."""

    q, i, e = getTestData(testfn)
    expected = getExpectedData(expectedfn)
    settings = dict(Q = q, I = i, IERR = numpy.maximum(0.01*i, e),
                    Ncontrib = 200, Nreps = 20,
                    Convcrit = 1, Maxiter = 1e5,
                    Histscale = 'log', drhosqr = 1e30,
                    Plot = False)
    # get number of repetitions+contributions from expected test data
    if isinstance(expected, dict):
        rrep = expected.get("Rrep", None)
        try:
            settings["Ncontrib"], dummy, settings["Nreps"] = tuple(rrep.shape)
        except:
            pass
    return settings, expected

def test():
    """Testing the algorithm in 1D. Atm, we just test as much as possible.
    Testing post-processing routines should be separated later
    as it's deterministic and though easier to test."""

    settings, expected = getSettings(FN_TEST_DATA, FN_EXPECTED_DATA)

    # run the monte carlo routine
    mcsas = McSAS(**settings)
    result = mcsas.result[0]

    if False:
        # print result keys and shape for debugging
        for key, item in result.iteritems():
            print(key, end="")
            try:
                print(item.shape)
            except:
                pass

    if expected is None:
        storeResultData(FN_EXPECTED_DATA, result)
        return # done here

    # testing against data from file
    # test only items which are averaged over all repetitions
    # individual tolerances because of large deviations for few repetitions(4)
    for key, tol in (("Hx", TOL), ("Hmid", TOL), ("Hwidth", TOL),
                     ("Hmean", 0.2), ("Hnmean", 0.2),
                     ("Hstd", 0.2), ("Hnstd", 0.2),
                     ("vfminbins", 0.01), ("nfminbins", 0.1),
                     ("Qfit", TOL), ("Imean", 0.005), ("Istd", 0.25)):
        print("testing {0:10} ".format(key), end="")
        assert isEqualFloat(result[key], expected[key], tol),\
            "Test for {0} failed!".format(key)

if __name__ == "__main__":
    test()

# vim: set ts=4 sts=4 sw=4 tw=0: