# -*- coding: utf-8 -*-
# models/gaussianchain.py

import numpy
from utils import mixedmethod
from utils.parameter import FitParameter, Parameter
from models import ScatteringModel
from cutesnake.algorithm import RandomUniform, RandomExponential

class GaussianChain(ScatteringModel):
    r"""Form factor of flexible polymer chains which are not selfavoiding
    and obey Gaussian statistics after [Debye47]_

    See also: http://sasfit.sf.net/manual/Gaussian_Chain#Gauss_2

    .. [Debye47] `P. Debye, Mollecular-weight determination by light
        scattering, Journal of Physical and Colloid Chemistry, 51:18--32,
        1947. <http://dx.doi.org/10.1021/j150451a002>`_

    I_0 = (bp - (k * Rg^2) * eta_s)^2 with k = 1 nm.
    k * Rg^2 = volume approximation
    """
    shortName = "Gaussian Chain"
    parameters = (
            FitParameter("rg", 1.0,
                    displayName = "radius of gyration, Rg",
                    generator = RandomExponential,
                    valueRange = (0., numpy.inf), suffix = "nm"),
            FitParameter("bp", 100.0,
                    displayName = "scattering length of the polymer",
                    generator = RandomUniform,
                    valueRange = (0., numpy.inf), suffix = "cm"),
            FitParameter("etas", 1.0,
                    displayName = "scattering length density of the solvent",
                    generator = RandomUniform,
                    valueRange = (0., numpy.inf), suffix = "cm<sup>-1</sup>"),
            FitParameter("k", 1.0,
                    displayName = "volumetric scaling factor of Rg",
                    generator = RandomUniform,
                    valueRange = (0., numpy.inf), suffix = "nm")
    )
    parameters[0].setActive(True)

    def __init__(self):
        super(GaussianChain, self).__init__()
        # some presets
        self.rg.setValueRange((1, 1e2))
        self.bp.setValueRange((0.1, 1e3))
        self.etas.setValueRange((0.1, 10.))
        self.k.setValueRange((0.1, 10.))

    def formfactor(self, dataset):
        # vectorized data
        beta = self.bp() - (self.k() * self.rg()**2) * self.etas()
        u = (dataset.q * self.rg())**2
        result = numpy.sqrt(2.) * numpy.sqrt(numpy.expm1(-u) + u) / u
        result *= beta
        result[dataset.q <= 0.0] = beta
        return result

    def volume(self):
        v = self.k() * self.rg()**2
        return v**self.compensationExponent

    @mixedmethod
    def fixTestParams(self, params):
        # order and meaning differs from sasfit Gauss2 model
        vol = params['etas']
        params['etas'] = params['k']
        params['k'] = vol / params['rg']**2.
        return params

GaussianChain.factory()

# testing for this model
# For testing with nose there needs to be a module level function containing
# *test* in its name. Run it like this:
#   PYTHONPATH=. nosetests --no-path-adjustment models/gaussianchain.py
# nosetest compatibility is required to enable automated testing and reporting
# of as much modules as possible ...
def test():
    GaussianChain.testRelErr = 1e-5
    # volume is already included in the model
    # volume is a difficult topic for this one anyway
    GaussianChain.testVolExp = 0.0
    for fn in ("sasfit_gauss2-5-1.5-2-1.dat",
               "sasfit_gauss2-1-100-1-1.dat"):
        yield GaussianChain.test, fn

# vim: set ts=4 sts=4 sw=4 tw=0:
