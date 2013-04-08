# -*- coding: utf-8 -*-
# McSAS.py
# Find the reST syntax at http://sphinx-doc.org/rest.html

r"""
Overview
========
A class and supplementary functions for Monte-Carlo fitting of SAXS patterns.
It is released under a `Creative Commons CC-BY-SA license
<http://creativecommons.org/licenses/by-sa/3.0/>`_.
Please cite as::

    Brian R. Pauw et al., J. Appl. Cryst. 46, (2013), pp. 365--371
        doi: http://dx.doi.org/10.1107/S0021889813001295

Classes and Functions Defined in This File
------------------------------------------

 - :py:class:`McSAS() <McSAS.McSAS>`:
   A class containing all the Functions required to perform a
   Monte Carlo analysis on small-angle scattering data.
 - :py:func:`binning_array`:
   Can be used to do n-by-n pixel binning of 2D detector
   images. The returned uncertainty is the larger of either the binned
   uncertainty or the sample standard deviation in the bin.
 - :py:func:`binning_1D`:
   bins the data and propagates errors, or calculates errors
   if not initially provided
 - :py:func:`binning_weighted_1D`:
   Weighted binning, where the intensities of a
   pixel are divided between the two neighbouring bins depending on the
   distances to the centres. If error provided is empty, the standard
   deviation of the intensities in the bins are computed.
 - :py:func:`pickle_read`:
   Reads in pickled data from a file (by filename)
 - :py:func:`pickle_write`:
   write a block or dictionary to a file (by filename)
    
Made possible with help from (amongst others)
---------------------------------------------

 - | Samuel Tardif
   | Derivations (mostly observability) and checking of mathematics
 - | Jan Skov Pedersen
   | checking of mathematics
 - | Pawel Kwasniewski <kwasniew@esrf.fr>
   | Code cleanup and documentation
 - | Ingo Bressler <ingo.bressler@bam.de>
   | Code cleanup, modification and documentation

A Note on Units
---------------

Internally, all length units are in meters, all angle units in degrees
clockwise from top. *Intensity* is in
:math:`\left[ 1 \over {m \cdot sr} \right]`,
*q* in :math:`\left[ 1 \over m \right]`.
The electron density contrast squared,
*drhosqr* is in :math:`\left[ m^{-4} \right]`.
Other units may be used, but if absolute units are supplied and absolute
volume fractions required, meters are necessitated.

Example Usage
-------------

*For detailed usage, please see the* :doc:`quickstart`

Fitting a single Dataset using all automatic and default Parameters
(may go wrong on poorly conditioned input, needs sensibly-spaced datapoints
and good uncertainty estimates).
The Dataset is considered to consist of three variables *Q*, *I* and *IERR*::

 McSAS(Q = Q, I = I, IERR = IERR, Plot = True)

Optional Parameters can be supplied in parameter-value pairs to finetune
optimisation behaviour::

 A = McSAS(Q = Q, I = I, IERR = numpy.maximum(0.01 * I, E),
           Ncontrib = 200, Convcrit = 1,
           Bounds = array([0.5e-9, 35e-9]),
           Maxiter = 1e5, Histscale = 'log',
           drhosqr = 1e30, Nreps = 100, Plot = True)

Module Documentation
====================
"""

import scipy # For many important Functions
from scipy import optimize # For the leastsq optimization function
import numpy # For arrays
from numpy import (inf, array, isfinite, reshape, prod, shape, pi, diff, zeros,
                  arange, size, sin, cos, sum, sqrt, linspace, logspace, log10,
                  isnan, ndim)
import os # Miscellaneous operating system interfaces
import time # Timekeeping and timing of objects
import sys # For printing of slightly more advanced messages to stdout
import pickle #for pickle_read and pickle_write

class McSAS(object):
    r"""
    Main class containing all functions required to do Monte Carlo fitting.

    **Required input Parameters:**

        - *Q*: 1D or 2D array of q-values
        - *I*: corresponding intensity values of the same shape
        - *IERR*: corresponding intensity uncertainty values of the same shape

    **Optional input Parameters:**

        - *PSI*: 2D array
            Detector angle values, only required for 2D pattern fitting.
        - *Bounds*: list
            Two-element vector or list indicating upper and lower size
            bounds of the particle radii used in the fitting procedure. If
            not provided, these will be estimated as:
            :math:`R_{max} = {pi \over q_{min}}` and
            :math:`R_{min} = {pi \over q_{max}}`. Units in meter.
        - *Ncontrib*: int, default: 200
            Number of spheres used for the MC simulation
        - *Maxiter*: int, default: 1e5
            Maximum number of iterations for the :py:func:`MCFit` function
        - *Rpfactor*: float, default: :math:`1.5 \over 3`
            Parameter used to compensate the :math:`volume^2` scaling of each
            sphere contribution to the simulated I(q).
        - *Nreps*: int, default: 100
            Number of repetitions of the MC fit for determination of final
            histogram uncertainty.
        - *qlims*: list, default: [0, inf]
            Limits on the fitting range in q.
            Units in :math:`m^{-1}`
        - *Histbins*: int, default: 50
            Number of bins used for the histogramming procedure.
        - *Histscale*: string, default: 'log'
            Can be set to 'log' for histogramming on a logarithmic size scale,
            recommended for q- and/or size-ranges spanning more than a decade.
        - *Histweight*: string, default: 'volume'
            Can be set to 'number' to force plotting of number-weighted
            distributions
        - *drhosqr*: float, default: 1
            Scattering contrast - when known it will be used to calculate the
            absolute volume fraction of each contribution.
            Units in :math:`m^{-4}`
        - *Convcrit*: float, default: 1
            Convergence criterion for the least-squares fit. The fit converges
            once the :math:`normalized \chi^2 < Convcrit`. If convergence is
            reached with `Convcrit == 1`, the model describes
            the data (on average) to within the uncertainty, and thus all
            information has been extracted from the scattering pattern.
        - *StartFromMin*: bool, default: False
            If set to False, the starting configuration is a set of spheres
            with radii uniformly sampled between the given or estimated
            bounds. If set to True, the starting configuration is a set of
            spheres with radii set to the lower given or estimated Bound
            (if not zero). Practically, this makes little difference and this
            feature might be depreciated.
        - *Maxntry*: int, default: 5
            If a single MC optimization fails to reach convergence within
            *Maxiter*, it may just be due to bad luck. The procedure will try
            to redo that MC optimization for a maximum of *Maxntry* tries
            before concluding that it is not bad luck but bad input.
        - *Plot*: Bool, default: False
            If set to True, will generate a plot showing the data and fit, as
            well as the Resulting size histogram.
        - *Memsave*: Bool, default: False
            For 2D pattern fitting, or for fitting patterns with a very large
            number of datapoints or contributions, it may make sense to turn
            this option on in order for intensity generating functions not to
            take up much memory. The cost for this is perhaps a 20-ish percent
            reduction in speed.
        - *BOUNDS*: string
            The McSAS function to use for calculating random number generator
            bounds based on input (f.ex. q and I).
            default: :py:func:`SphBounds`
        - *FF*: string
            The McSAS function to use for calculating the form factors.
            default: :py:func:`FF_sph_1D`
        - *RAND*: string
            the McSAS function to use for generating random numbers
            default: :py:func:`random_uniform_sph`
        - *SMEAR*: string
            the McSAS function to use for smearing of intensity
            default: :py:func:`_passthrough`
        - *VOL*: string
            the McSAS function to use for calculating the base object volume
            default: :py:func:`vol_sph`

    **Returns:**

    A McSAS object with the following Results stored in the *Result* member
    attribute. These can be extracted using
    McSAS.GetResult('Keyword',VariableNumber=0)
    where the *VariableNumber* indicates which shape parameter information is
    requested for
    (some information is only stored in *VariableNumber = 0* (default)).

    **Keyword** may be one of the following:

        *Imean*: 1D array (*VariableNumber = 0*)
            The fitted intensity, given as the mean of all Nreps Results.
        *q*: 1D array (*VariableNumber = 0*)
            Corresponding q values
            (may be different than the input q if *qlims* was used).
        *Istd*: array (*VariableNumber = 0*)
            Standard deviation of the fitted I(q), calculated as the standard 
            deviation of all Nreps Results.
        *Rrep*: size array (Ncontrib x Nreps) (*VariableNumber = 0*)
            Collection of Ncontrib contributions fitted to best represent the
            provided I(q) data. Contains the Results of each of *Nreps*
            iterations. This can be used for rebinning without having to
            re-optimize.
        *Screps*: size array (2 x Nreps) (*VariableNumber = 0*)
            Scaling and background values for each repetition.
            Used to display background level in data and fit plot.
        *VariableNumber*: int
            Shape parameter index.
            E.g. an ellipsoid has 3: width, height and orientation.
        *Hx*: array
            Histogram bin left edge position (x-axis in histogram).
        *Hmid*: array
            Center positions for the size histogram bins
            (x-axis in histogram, used for errorbars).
        *Hwidth*: array
            Histogram bin width
            (x-axis in histogram, defines bar plot bar widths).
        *Hmean*: array
            Volume-weighted particle size distribution values for
            all Nreps Results (y-axis bar height).
        *Hnmean*: array
            Number-weighted analogue of the above *Hmean*.
        *Hy*: size array (Histbins x Nreps)
            Volume-weighted particle size distribution bin values for
            each MC fit repetition (the mean of which is *Hmean*, and the
            sample standard deviation of which is *Hstd*).
        *Hny*: size array (Histbins x Nreps)
            Number-weighted particle size distribution bin values for
            each MC fit repetition.
        *Hstd*: array
            Standard deviations of the corresponding volume-weighted size
            distribution bins, calculated from *Nreps* repetitions of the
            :py:meth:`McSAS.MCfit_sph` function.
        *Hnstd*: array
            Standard deviation for the number-weigthed distribution.
        *Vf*: size array (Ncontrib x Nreps)
            Volume fractions for each of Ncontrib contributions in each of
            *Nreps* iterations.
        *Nf*: size array (Ncontrib x Nreps)
            Number fraction for each contribution.
        *Vft*: size array (Nreps)
            Total scatterer volume fraction for each of the Nreps iterations.
        *Nft*: size array (Nreps)
            Total number fraction.
        *vfmin*: size array (Ncontrib x Nreps)
            Minimum required volume fraction for each contribution to become
            statistically significant.
        *nfmin*: size array (Ncontrib x Nreps)
            Number-weighted analogue to *vfmin*.
        *vfminbins*: size array (Hmid)
            Array with the minimum required volume fraction per bin to become
            statistically significant. Used to display minimum required level
            in histogram.
        *nfminbins*: size array (Hmid)
            Number-weighted analogue to *vfminbins*.
        *Screps*: size array (2 x Nreps)
            Scaling and background values for each repetition. Used to display
            background level in data and fit plot.
        *Vf*: size array (Ncontrib x Nreps)
            Volume fractions for each of *Ncontrib* spheres in each of *Nreps*
            iterations.
        *Vft*: size array (Nreps)
            Total scatterer volume fraction for each of the *Nreps*
            iterations.
        *vfmin*: size array (Ncontrib x Nreps)
            Minimum required volube fraction for each contribution to become
            statistically significant.
        *vfminbins*: size array (Hmid)
            Array with the minimum required volume fraction per bin to become
            statistically significant. Used to display minimum required level
            in histogram.

    **Internal Variables**
    
    :py:attr:`self.Dataset`
        Where Q, PSI, I and IERR is stored, original Dataset.
    :py:attr:`self.FitData`
        May be populated with a subset of the aforementioned Dataset, limited
        to q-limits or psi limits and to positive I values alone.
    :py:attr:`self.Parameters`
        Where the fitting and binning settings are stored.
    :py:attr:`self.Result`
        Where all the analysis Results are stored. I do not think this needs
        separation after all into Results of analysis and Results of
        interpretation. However, this is a list of dicts, one per variable
        (as the method, especially for 2D analysis, can deal with more than
        one random values. analysis Results are stored along with the
        histogrammed Results of the first variable with index [0]:
    :py:attr:`self.Functions`
        Where the used functions are defined, this is where shape changes,
        smearing, and various forms of integrations are placed.

    :py:attr:`self.`
    :py:attr:`self.`
    """

    Dataset = None
    FitData = None
    Parameters = None
    Result = None
    Functions = None

    def __init__(self, **kwargs):
        """
        The constructor, takes keyword-value input Parameters. They can be
        one of the aforementioned parameter keyword-value pairs.
        This does the following:

            1. Initialises the variables to the right type
            2. Parses the input
            3. Stores the supplied data twice, one original and one for fitting
                (the latter of which may be clipped or otherwise adjusted)
            4. Applies Q- and optional PSI- limits to the data
            5. Reshapes FitData to 1-by-n dimensions
            6. Sets the function references
            7. Calculates the shape parameter bounds if not supplied
            8. Peforms simple checks on validity of input
            9. Runs the Analyse() function which applies the MC fit multiple
               times
            10. Runs the Histogram() procedure which processes the MC result
            11. Optionally recalculates the resulting intensity in the same
                shape as the original (for 2D Datasets)
            12. Optionally displays the results graphically.

        .. document private Functions
        .. automethod:: _Iopt
        """
        # initialize
        self.Dataset = dict()
        self.FitData = dict()
        self.Parameters = dict()
        self.Result = list()
        self.Result.append(dict())
        self.Functions = dict()

        # populate self with defaults
        self.SetDefaults()
        # set supplied kwargs and passing on
        self.SetParameter(**kwargs)
        # set data values
        self.SetData(**kwargs)
        # apply q and psi limits and populate self.FitData
        self.ClipDataset()
        # reshape FitData to the correct 1-by-n dimensions
        self.ReshapeFitdata()
        # apply input settings for fitting,
        # setting the required function definitions
        self.SetFunction(**kwargs)
        # calculate parameter bounds and store
        self.GetFunction('BOUNDS')()
        # check and fix Parameters where necessary
        # This is only a very simple function now in need of expansion
        self.CheckParameters()

        self.Analyse()
        self.Histogram()

        if ndim(kwargs['Q']) > 1:
            # 2D mode, regenerate intensity
            self.GenerateTwoDIntensity()

        if self.GetParameter('Plot'):
            # Odata = self.GetData(Dataset = 'original')
            # Result = self.GetResult()
            self.Plot()

    ######################################################################
    ##################### Pre-optimisation Functions #####################
    ######################################################################
    def SetDefaults(self):
        """
        Populates the default parameter settings
        """
        # field names
        # fnames = list(['Bounds', 'Ncontrib', 'Maxiter', 'Rpfactor', 'Nreps',
        #                'qlims', 'psilims', 'Histbins', 'Histscale',
        #                'drhosqr', 'Convcrit', 'StartFromMin', 'Maxntry'])
        self.Parameters = {
            'Bounds': [],
            'Ncontrib': 200,
            'Maxiter': 1e5,
            'Rpfactor': 0.5,
            'Nreps': 100,
            'qlims': [],
            'psilims': [],
            'Priors': [], # of shape Rrep, to be used as initial guess for
                          # Analyse function, Analyse will pass on a Prior
                          # to MCFit.
            'Prior': [], # of shape Rset, to be used as initial guess for
                         # MCFit function
            'Histbins': 50,
            'Histscale': 'log',
            'Histweight': 'volume', # can be set to "volume" or "number"
            'drhosqr': 1,
            'Convcrit': 1.,
            'StartFromMin': False,
            'Maxntry': 5,
            'MaskNegI': False,
            'MaskZeroI': False,
            'Memsave': False,
            'Plot': False
        }

        self.Functions = {
            'BOUNDS': self.SphBounds, # this function has to give a vector
                                      # the size of the number of
                                      # variables *2 (lower and upper)
            'RAND': self.random_uniform_sph,
            'FF': self.FF_sph_1D, # 1D spheres
            'VOL': self.vol_sph,
            'SMEAR': self._passthrough # None
        }

    def SetFunction(self, **kwargs):
        """Defines Functions. In particular the following are specified:

        - The parameter bounds estimation function *BOUNDS*. Should be able
          to take input argument Bounds to update, should set the parameter
          bounds in ``self.parameter['Bounds']``

        - The random number generation function *RAND* This must take its
          Parameters from self, and have an optional input argument specifying
          the number of sets to return (for MC initialization). It should
          return a set of Nsets-by-nvalues to be used directly in *FF*. This
          may be depreciated soon as is can be generated from within.

        - The Form-factor function *FF*. If called, this should get the
          required information from self and a supplied Nsets-by-nvalues
          shape-specifying parameter array. It should return an Nsets-by-q
          array. Orientational averaging should be part of the form-factor
          function (as it is most efficiently calculated there), so several
          form factor Functions can exist for non-spherical objects.

        - The shape volume calculation function *VOL*, which must be able to
          deal with input argument *Rpfactor*, ranging from 0 to 1. Should
          accept an Nsets-by-nvalues array returning an Nsets number of
          (Rpfactor-compensated)-volumes. 

        - The smearing function *SMEAR*. Should take information from self
          and an input Icalc, to output an Ismear of the same length.

        This function will actually use the supplied function name as function
        reference.
        """
        for kw in kwargs:
            if kw in self.Functions.keys():
                if callable(kwargs[kw]):
                    self.Functions[kw] = kwargs[kw]
                else:
                    # Make it into a function handle/pointer.
                    self.Functions[kw] = getattr(self, kwargs[kw])

    def GetFunction(self, fname = None):
        """Returns the function handle or all handles (if no function name
        supplied).
        
        :param fname: can be one of the following: <TODO>
        """
        fname = fname.upper()
        if not fname in self.Functions.keys():
            print "Unknown function identifier {}".format(fname)
            return None
        if fname == None:
            return self.Functions
        else:
            return self.Functions[fname]



    def ReshapeFitdata(self):
        """This ensures that q, I, PSI and E are in 1-by-n shape."""
        for key in self.FitData.keys():
            self.FitData[key] = reshape(self.FitData[key],
                                        (1, prod(shape(self.FitData[key]))))

    def ClipDataset(self):
        """If q and/or psi limits are supplied in self.Parameters,
        clips the Dataset to within the supplied limits. Copies data to
        :py:attr:`self.FitData` if no limits are set.
        """
        qlims = self.GetParameter('qlims')
        psilims = self.GetParameter('psilims')
        Dataset = self.GetData(Dataset = 'original')
        
        validbools = isfinite(Dataset['Q'])
        # Optional masking of negative intensity
        if self.GetParameter('MaskNegI'):
            validbools = validbools * (Dataset['I'] >= 0)
        if self.GetParameter('MaskZeroI'):
            validbools = validbools * (Dataset['I'] != 0)
        if (qlims == []) and (psilims == []):
            # q limits not set, simply copy Dataset to FitData
            validbools = validbools
        if (not(qlims == [])): # and qlims is implicitly set
            # excluding the lower q limit may prevent q = 0 from appearing
            validbools = validbools * ((Dataset['Q'] >  numpy.min(qlims)) &
                                       (Dataset['Q'] <= numpy.max(qlims)))
        if (not(psilims==[])):
            # we assume here that we have a Dataset ['PSI']
            # excluding the lower q limit may prevent q = 0 from appearing
            validbools = validbools * ((Dataset['PSI'] >  numpy.min(psilims)) &
                                       (Dataset['PSI'] <= numpy.max(psilims)))

        for key in Dataset.keys():
            dsk = Dataset[key][validbools]
            # hey, this works!:
            self.SetData(**{ key: dsk, 'Dataset': 'fit' })
            # old version was direct addressing, which is to be discouraged to
            # encourage flexibility in data storage
            # self.FitData[key] = Dataset[key][validbools]

        # self.FitData = FitData
        
    def GetParameter(self, parname = []):
        """Gets the value of a parameter, so simple it is probably
        superfluous.
        """
        if parname == []:
            return self.Parameters
        else:
            return self.Parameters[parname]

    def GetData(self, parname = [], Dataset = 'fit'):
        """Gets the values of a Dataset, retrieves from FitData (clipped)
        by default. If the original data is wanted,
        use ``Dataset = 'original'`` as *\*\*kwarg*.
        """
        if (parname == []):
            if (Dataset == 'fit'):
                return self.FitData
            else: 
                return self.Dataset
        else:
            if (parname in self.FitData.keys()) and (Dataset == 'fit'):
                return self.FitData[parname]
            else:
                return self.Dataset[parname]

    def GetResult(self, parname = [], VariableNumber = 0):
        """Returns the specified entry from common Result container."""
        if parname == []:
            return self.Result[VariableNumber]
        else:
            return self.Result[VariableNumber][parname]

    def SetResult(self, **kwargs):
        """Sets the supplied keyword-value pairs to the Result. These can be
        arbitrary. Varnum is the sequence number of the variable for which
        data is stored. Default is set to 0, which is where the output of the
        MC routine is put before histogramming. The Histogramming procedure
        may populate more variables if so needed.
        """
        if 'VariableNumber' in kwargs.keys():
            varnum = kwargs['VariableNumber']
        else:
            varnum = 0

        while len(self.Result) < (varnum + 1):
            # make sure there is a dictionary in the location we want to save
            # the Result to
            self.Result.append(dict())
        
        rdict = self.Result[varnum]

        for kw in kwargs:
            rdict[kw] = kwargs[kw]

    def SetParameter(self, **kwargs):
        """Sets the supplied Parameters given in keyword-value pairs for known
        setting keywords (unknown key-value pairs are skipped).
        If a supplied parameter is one of the function names, it is stored in
        the self.Functions dict.
        """
        for kw in kwargs:
            if kw in self.Parameters.keys():
                self.Parameters[kw] = kwargs[kw]
            else:
                pass #no need to store unknown keywords.

    def SetData(self, **kwargs):
        """Sets the supplied data in the proper location. Optional argument
        *Dataset* can be set to ``fit`` or ``original`` to define which
        Dataset is set. Default is ``original``.
        """
        Datasetlist = list(['Q', 'I', 'PSI', 'IERR']) # list of valid things
        if ('Dataset' in kwargs):
            Dataset = kwargs['Dataset'].lower()
        else:
            Dataset = 'original'
        if Dataset not in ('fit', 'original'):
            Dataset = 'original'

        if Dataset == 'original':
            for kw in kwargs:
                if kw in Datasetlist:
                    self.Dataset[kw] = kwargs[kw]
                else:
                    pass # do not store non-Dataset values.
        else: # we want to store to FitData: a clipped Dataset
            for kw in kwargs:
                if kw in Datasetlist:
                    self.FitData[kw] = kwargs[kw]
                else:
                    pass # Do not store non-Dataset values.

    def CheckParameters(self):
        """Checks for the Parameters, for example to make sure
        histbins is defined for all, or to check if all Parameters fall
        within their limits.
        For now, all I need is a check that Histbins is a 1D vector
        with n values, where n is the number of Parameters specifying
        a shape.
        """
        # testR = self.Functions['RAND']()
        testR = self.GetFunction('RAND')()
        NRval = prod(shape(testR))
        Histbins = self.GetParameter('Histbins')
        if not(isinstance(Histbins, list)): # meaning it will be a string
            HB = list()
            for ri in range(NRval):
                HB.append(int(Histbins))
            self.SetParameter(Histbins = HB)
        elif len(Histbins) < NRval:
            # histbins is a list but not of the right length
            while len(Histscale) < NRval:
                Histbins.append(Histbins[0])
            self.SetParameter(Histbins = Histbins)
        # now check histscale
        Histscale = self.GetParameter('Histscale')
        if not(isinstance(Histscale, list)): # meaning it will be a string
            HS = list()
            for ri in range(NRval):
                HS.append(Histscale) # repeat until we have enough
            # replace histscale
            self.SetParameter(Histscale = HS)
        elif len(Histscale) < NRval:
            # histscale is a list but not of the right length
            while len(Histscale) < NRval:
                Histscale.append(Histscale[0])
            self.SetParameter(Histscale = Histscale)

    def _Iopt(self, I, Ic, E, Sc, ver = 2,
              OutputI = False, Background = True):
        """
        Optimizes the scaling and background factor to match Ic closest to I.
        Returns an array with scaling factors. Input initial guess *Sc* has 
        to be a two-element array with the scaling and background.

        **Input arguments:**

        :arg I: An array of *measured* intensities
        :arg Ic: An array of intensities which should be scaled to match *I*
        :arg E: An array of uncertainties to match *I*
        :arg Sc: A 2-element array of initial guesses for scaling
                 factor and background
        :arg ver: *(optional)* Can be set to 1 for old version, more robust
                  but slow, default 2 for new version,
                  10x faster than version 1
        :arg OutputI: *(optional)* Return the scaled intensity as third output
                      argument, default: False
        :arg Background: *(optional)* Enables a flat background contribution,
                         default: True

        :returns: (*Sc*, *cval*): A tuple of an array containing the intensity
            scaling factor and background and the reduced chi-squared value.
        """
        def csqr(Sc, I, Ic, E):
            """Least-squares error for use with scipy.optimize.leastsq"""
            cs = (I - Sc[0]*Ic - Sc[1]) / E
            return cs
        
        def csqr_noBG(Sc, I, Ic, E):
            """Least-squares error for use with scipy.optimize.leastsq,
            without background """
            cs = (I - Sc[0]*Ic) / E
            return cs

        def csqr_v1(I, Ic, E):
            """Least-squares for data with known error,
            size of parameter-space not taken into account."""
            cs = sum(((I - Ic)/E)**2) / size(I)
            return cs

        if ver == 2:
            """uses scipy.optimize.leastsqr"""
            if Background:
                Sc, success = scipy.optimize.leastsq(csqr, Sc,
                                                     args = (I.flatten(),
                                                             Ic.flatten(),
                                                             E.flatten()),
                                                            full_output = 0)
                cval = csqr_v1(I, Sc[0]*Ic + Sc[1], E)
            else:
                Sc, success = scipy.optimize.leastsq(csqr_noBG, Sc,
                                                     args = (I.flatten(),
                                                             Ic.flatten(),
                                                             E.flatten()),
                                                            full_output = 0)
                Sc[1] = 0.0
                cval = csqr_v1(I, Sc[0]*Ic, E)
        else:
            """using scipy.optimize.fmin"""
            # Background can be set to False to just find the scaling factor.
            if Background:
                Sc = scipy.optimize.fmin(
                        lambda Sc: csqr_v1(I, Sc[0]*Ic + Sc[1], E),
                        Sc, full_output = 0, disp = 0)
                cval = csqr_v1(I, Sc[0]*Ic + Sc[1], E)
            else:
                Sc = scipy.optimize.fmin(
                        lambda Sc: csqr_v1(I, Sc[0]*Ic, E),
                        Sc, full_output = 0, disp = 0)
                Sc[1] = 0.0
                cval = csqr_v1(I, Sc[0]*Ic, E)

        if OutputI:
            return Sc, cval, Sc[0]*Ic + Sc[1]
        else:
            return Sc, cval

    ######################## Shape Functions ######################
    def EllBounds_2D(self):
        """This function will take the q and psi input bounds and outputs
        properly formatted two-element size bounds for ellipsoids. Ellipsoids
        are defined by their equatorial radius, meridional radius and axis
        misalignment (default -45 to 45 degrees in PSI).
        """
        Bounds = self.GetParameter('Bounds')
        q = self.GetData('Q')
        # reasonable, but not necessarily correct, Parameters
        qBounds = array([pi / numpy.max(q),
                         pi / numpy.min((abs(numpy.min(q)),
                                       abs(numpy.min(diff(q)))))])
        if len(Bounds) == 0:
            print "Bounds not provided, so set related to minimum q or " \
                  "minimum q step and maximum q. Lower and upper bounds " \
                  "are {0} and {1}".format(qBounds[0], qBounds[1])
            Bounds = numpy.array([qBounds[0], qBounds[1],
                                  qBounds[0], qBounds[1],
                                  -45, 45])
        elif len(Bounds) == 6:
            pass
            #print 'Bounds provided, set to {} and {}'.format(
            #    Bounds[0], Bounds[1])
        else:
            print "Wrong number of Bounds provided, defaulting to {}" \
                  "and {} for radii, -45, 45 for misalignment" \
                  .format(qBounds[0], qBounds[1])
            Bounds = numpy.array([qBounds[0], qBounds[1],
                                  qBounds[0], qBounds[1],
                                  -45, 45])
        Bounds = numpy.array([numpy.min(Bounds[0:2]), numpy.max(Bounds[0:2]),
                              numpy.min(Bounds[2:4]), numpy.max(Bounds[2:4]),
                              numpy.min(Bounds[4:6]), numpy.max(Bounds[4:6])])

        self.SetParameter(Bounds = Bounds)

    def SphBounds(self):
        """This function will take the q and input bounds and outputs properly
        formatted two-element size bounds.
        """
        Bounds = self.GetParameter('Bounds')
        q = self.GetData('Q')
        # reasonable, but not necessarily correct, Parameters
        qBounds = array([pi/numpy.max(q),
                         pi/numpy.min((abs(numpy.min(q)),
                                       abs(numpy.min(diff(q)))))])
        if len(Bounds) == 0:
            print "Bounds not provided, so set related to minimum q or "\
                  "minimum q step and maximum q. Lower and upper bounds "\
                  "are {0} and {1}".format(qBounds[0], qBounds[1])
            Bounds = qBounds
        elif len(Bounds) == 1:
            print "Only one bound provided, assuming it denotes the maximum."\
                  " Lower and upper bounds are set to {0} and {1}"\
                  .format(qBounds[0], Bounds[1])
            Bounds = numpy.array([qBounds[0], Bounds])
        elif len(Bounds) == 2:
            pass
            # print 'Bounds provided, set to {} and {}'\
            #        .format(Bounds[0],Bounds[1])
        else:
            print "Wrong number of Bounds provided, defaulting to {} and {}"\
                  .format(qBounds[0], qBounds[1])
            Bounds = qbounds
        Bounds = numpy.array([numpy.min(Bounds), numpy.max(Bounds)])
        self.SetParameter(Bounds = Bounds)

    def random_uniform_ell(self, Nell = 1):
        """Random number generator for generating uniformly-sampled
        size- and orientation Parameters for ellipsoids.
        """
        # get Parameters from self
        Bounds = self.GetParameter('Bounds') 
        # generate Nsph random numbers
        Rset = zeros((Nell, 3))
        Rset[:, 0] = numpy.random.uniform(numpy.min(Bounds[0]),
                                          numpy.max(Bounds[1]), Nell)
        Rset[:, 1] = numpy.random.uniform(numpy.min(Bounds[2]),
                                          numpy.max(Bounds[3]), Nell)
        Rset[:, 2] = numpy.random.uniform(numpy.min(Bounds[4]),
                                          numpy.max(Bounds[5]), Nell)
        # output Nsph-by-3 array
        return Rset

    def random_logR_ell(self, Nell = 1):
        """Random number generator which behaves like its uniform counterpart,
        but with a higher likelihood of sampling smaller sizes.
        May speed up some fitting procedures.
        """
        #get Parameters from self
        Bounds = self.GetParameter('Bounds')
        #generate Nsph random numbers
        Rset = zeros((Nell, 3))
        Rset[:, 0] = 10**(numpy.random.uniform(log10(numpy.min(Bounds[0])),
                                               log10(numpy.max(Bounds[1])),
                                               Nell))
        Rset[:, 1] = 10**(numpy.random.uniform(log10(numpy.min(Bounds[2])),
                                               log10(numpy.max(Bounds[3])),
                                               Nell))
        Rset[:, 2] = numpy.random.uniform(numpy.min(Bounds[4]),
                                          numpy.max(Bounds[5]), Nell)
        # output Nsph-by-3 array
        return Rset

    def random_logR_oblate_ell(self, Nell = 1):
        """Random number generator which behaves like its uniform counterpart,
        but with a higher likelihood of sampling smaller sizes.
        May speed up some fitting procedures.
        """
        # get Parameters from self
        Bounds = self.GetParameter('Bounds')
        # generate Nsph random numbers
        Rset = zeros((Nell, 3))
        Rset[:, 0] = 10**(numpy.random.uniform(log10(numpy.min(Bounds[0])),
                                               log10(numpy.max(Bounds[1])),
                                               Nell))
        for Ni in range(Nell):
            Rset[Ni, 1] = 10**(numpy.random.uniform(
                                    log10(numpy.min(Bounds[2])),
                                    log10(numpy.minimum(Bounds[3],
                                                        Rset[Ni,0])), 1))
        Rset[:,2]=numpy.random.uniform(numpy.min(Bounds[4]),
                                       numpy.max(Bounds[5]), Nell)
        # output Nsph-by-3 array
        return Rset

    def random_logR_prolate_ell(self, Nell = 1):
        """Random number generator which behaves like its uniform counterpart,
        but with a higher likelihood of sampling smaller sizes.
        May speed up some fitting procedures.
        """
        # get Parameters from self
        Bounds = self.GetParameter('Bounds')
        # generate Nsph random numbers
        Rset = zeros((Nell, 3))
        Rset[:, 0] = 10**(numpy.random.uniform(
                            log10(numpy.min(Bounds[0])),
                            log10(numpy.max(Bounds[1])), Nell))
        for Ni in range(Nell):
            Rset[Ni, 1] = 10**(numpy.random.uniform(
                                log10(numpy.maximum(Rset[Ni, 0], Bounds[2])),
                                log10(Bounds[3]), 1))
        Rset[:, 2] = numpy.random.uniform(numpy.min(Bounds[4]),
                                          numpy.max(Bounds[5]), Nell)
        # output Nsph-by-3 array
        return Rset

    def random_logR_sph(self, Nsph = 1):
        """Random number generator with logarithmic probabilistic sampling."""
        # get Parameters from self
        Bounds = self.GetParameter('Bounds')
        # generate Nsph random numbers
        Rset = 10**(numpy.random.uniform(log10(numpy.min(Bounds)),
                                         log10(numpy.max(Bounds)), Nsph))
        Rset = reshape(Rset, (prod(shape(Rset)), 1))
        # output Nsph-by-1 array
        return Rset

    def random_uniform_sph(self, Nsph = 1):
        """Random number generator with uniform distribution for
        the sphere form factor."""
        # get Parameters from self
        Bounds = self.GetParameter('Bounds')
        # generate Nsph random numbers
        Rset = numpy.random.uniform(numpy.min(Bounds),
                                    numpy.max(Bounds), Nsph)
        Rset = reshape(Rset, (prod(shape(Rset)), 1))
        # output Nsph-by-1 array
        return Rset

    def vol_ell(self, Rset, Rpfactor = []):
        """Calculates the volume of an ellipsoid, taking Rpfactor from input
        or preset Parameters.
        """
        if Rpfactor == []:
            Rpfactor = self.GetParameter('Rpfactor')
        return ((4.0/3*pi) * Rset[:, 0]**(2*Rpfactor) * Rset[:, 1]**(Rpfactor)
                )[:, newaxis]

    def vol_sph(self, Rset, Rpfactor = []):
        """Calculates the volume of a sphere, taking Rpfactor from input
        or preset Parameters.
        """
        if Rpfactor == []:
            Rpfactor = self.GetParameter('Rpfactor')
        return (4.0/3*pi) * Rset**(3*Rpfactor)

    def FF_sph_1D(self, Rset):
        """Calculate the Rayleigh function for a sphere.
        """
        q = self.GetData('Q')
        if size(Rset, 0) > 1:
            # multimensional matrices required, input Rsph has to be Nsph-by-1.
            # q has to be 1-by-N
            qR = (q + 0*Rset) * (Rset + 0*q)
        else:
            qR = (q) * (Rset)

        Fsph = 3 * (sin(qR) - qR * cos(qR)) / (qR**3)
        return Fsph

    def FF_ell_2D(self, Rset = [], Q = [], PSI = []):
        """Calculates the form factor for oriented ellipsoids,
        normalized to 1 at Q = 0.

        :arg Rset: is n-by-3::

                R1 = Rset[:, 0]
                R2 = Rset[:, 1]
                R3 = Rset[:, 2]

            **R1 < R2**:
                prolate ellipsoid (cigar-shaped)
            **R1 > R2**:
                oblate ellipsoid (disk-shaped)
        
        Rotation is offset from perfect orientation (psi-rot)

        **Note**: All 2D Functions should be able to potentially take
        externally supplied Q and PSI vectors.
        """
        # degrees to radians, forget the dot and get yourself into a
        # non-floating point mess, even though pi is floating point ...
        d_to_r = 1. / 360 * 2 * pi
        if Q == []:
            q = self.GetData('Q')     # 1-by-N
            psi = self.GetData('PSI') # 1-by-N
        else:
            # externally supplied data
            q = Q
            psi = PSI
        R1, R2, rot = Rset[:, 0], Rset[:, 1], Rset[:, 2]
        NR = prod(shape(R1))
        if NR == 1:
            # option 1:
            sda = sin((psi-rot) * d_to_r)
            cda = cos((psi-rot) * d_to_r)
            r = sqrt(R1**2 * sda**2 + R2**2 * cda**2)
            qr = q*r
            Fell = 3*(sin(qr) - qr*cos(qr)) / (qr**3)
            ##quicker? no, 20% slower:
            #Fell=3*(
            #        sin(q*sqrt(R1**2*sin((psi-rot)*d_to_r)**2
            #            +R2**2*cos((psi-rot)*d_to_r)**2))
            #        -q*sqrt(R1**2*sin((psi-rot)*d_to_r)**2
            #            +R2**2*cos((psi-rot)*d_to_r)**2)
            #        *cos(q*sqrt(R1**2*sin((psi-rot)*d_to_r)**2
            #            +R2**2*cos((psi-rot)*d_to_r)**2)))/
            #               ((q*sqrt(R1**2*sin((psi-rot)*d_to_r)**2
            #                +R2**2*cos((psi-rot)*d_to_r)**2))**3)
        else: # calculate a series
            Fell = zeros([NR, prod(shape(q))])
            for Ri in range(size(R1)):
                sda = sin((psi-rot[Ri]) * d_to_r)
                cda = cos((psi-rot[Ri]) * d_to_r)
                r = sqrt(R1[Ri]**2 * sda**2 + R2[Ri]**2 * cda**2)
                qr = q*r
                Fell[Ri, :] = 3*(sin(qr) - qr*cos(qr)) / (qr**3)

        return Fell # this will be n-by-len(q) array

    def _passthrough(self,In):
        """A passthrough mechanism returning the input unchanged"""
        return In


    ######################################################################
    ####################### optimisation Functions #######################
    ######################################################################

    def Analyse(self):
        """This function runs the Monte Carlo optimisation a multitude
        (*Nreps*) of times. If convergence is not achieved, it will try again
        for a maximum of *Maxntry* attempts.
        """
        # get data
        q = self.GetData('Q')
        I = self.GetData('I')
        E = self.GetData('IERR')
        # get settings
        Priors = self.GetParameter('Priors')
        Prior = self.GetParameter('Prior')
        Ncontrib = self.GetParameter('Ncontrib')
        Nreps = self.GetParameter('Nreps')
        Convcrit = self.GetParameter('Convcrit')
        Maxntry = self.GetParameter('Maxntry')
        # find out how many values a shape is defined by:
        # testR = self.Functions['RAND']()
        testR = self.GetFunction('RAND')()
        NRval = prod(shape((testR)))
        Rrep = zeros([Ncontrib, NRval, Nreps])
        # DEBUG:
        # print 'Rrep: {}'.format(shape(Rrep))
        Niters = zeros([Nreps])
        Irep = zeros([1, prod(shape(I)), Nreps])
        bignow = time.time() # for time estimation and reporting

        # This is the loop that repeats the MC optimization Nreps times,
        # after which we can calculate an uncertainty on the Results.
        priorsflag = False
        for nr in arange(0, Nreps):
            if ((Prior == []) and (Priors != [])) or (priorsflag == True):
                # this flag needs to be set as prior will be set after
                # the first pass
                priorsflag = True
                self.SetParameter(Prior = Priors[:, :, nr%size(Priors, 2)])
            # keep track of how many failed attempts there have been
            nt = 0
            # do that MC thing! 
            ConVal = inf
            while ConVal > Convcrit:
                # retry in the case we were unlucky in reaching
                # convergence within Maxiter.
                nt += 1
                Rrep[:, :, nr], Irep[:, :, nr], ConVal, Details = \
                        self.MCFit(OutputI = True, OutputDetails = True)
                if nt > Maxntry:
                    # this is not a coincidence.
                    # We have now tried Maxntry+2 times
                    print "could not reach optimization criterion within "\
                          "{0} attempts, exiting...".format(Maxntry+2)
                    return
            # keep track of how many iterations were needed to reach converg.
            Niters[nr] = Details['Niter']

            biglap = time.time() # time management
            # in minutes:
            tottime = (biglap-bignow)/60. # total elapsed time
            avetime = (tottime/ (nr+1)) # average time per MC optimization
            remtime = (avetime*Nreps - tottime) # estimated remaining time
            print "\t*finished optimization number {0} of {1} \r\n"\
                  "\t*total elapsed time: {2} minutes \r\n"\
                  "\t*average time per optimization {3} minutes \r\n"\
                  "\t*total time remaining {4} minutes"\
                  .format(nr+1, Nreps, tottime, avetime, remtime)
        
        # at this point, all MC optimizations have been completed and
        # we can process all Nreps Results.
        Imean = numpy.mean(Irep, axis = 2) # mean fitted intensity
        # standard deviation on the fitted intensity,
        # usually not plotted for clarity
        Istd = numpy.std(Irep, axis = 2)
        # store in output dict
        self.SetResult(**{
            'Rrep': Rrep,
            'Imean': Imean,
            'Istd': Istd,
            'Qfit': q, # can be obtained from self.FitData 
            #average number of iterations for all repetitions
            'Niter': numpy.mean(Niters)})

    def MCFit(self, OutputI = False,
                    OutputDetails = False, OutputIterations = False):
        """
        Object-oriented, shape-flexible core of the Monte Carlo procedure.
        Takes optional arguments:

        *OutputI*:
            Returns the fitted intensity besides the Result

        *OutputDetails*:
            Details of the fitting procedure, number of iterations and so on

        *OutputIterations*:
            Returns the Result on every successful iteration step, useful for
            visualising the entire Monte Carlo optimisation procedure for
            presentations.
        """
        # load Dataset
        q = self.GetData('Q')
        I = self.GetData('I')
        E = self.GetData('IERR')
        # load Parameters
        Ncontrib = self.GetParameter('Ncontrib')
        Bounds = self.GetParameter('Bounds')
        Convcrit = self.GetParameter('Convcrit')
        Rpfactor = self.GetParameter('Rpfactor')
        Maxiter = self.GetParameter('Maxiter')
        MaskNegI = self.GetParameter('MaskNegI')
        MaskZeroI = self.GetParameter('MaskZeroI')
        StartFromMin = self.GetParameter('StartFromMin')
        Memsave = self.GetParameter('Memsave')
        Prior = self.GetParameter('Prior')

        # find out how many values a shape is defined by:
        Randfunc = self.GetFunction('RAND')
        FFfunc = self.GetFunction('FF')
        VOLfunc = self.GetFunction('VOL')
        SMEARfunc = self.GetFunction('SMEAR')
        testR = Randfunc()
        NRval = prod(shape(testR))

        Rset = numpy.zeros((Ncontrib, NRval))

        # Intialise variables
        FFset = []
        Vset = []
        Niter = 0
        Conval = inf
        Details = dict()
        # index of sphere to change. We'll sequentially change spheres,
        # which is perfectly random since they are in random order.
        Ri = 0
        
        # generate initial set of spheres
        if size(Prior) == 0:
            if StartFromMin:
                for Rvi in range(NRval): # minimum bound for each value
                    if numpy.min(Bounds[Rvi:Rvi+2]) == 0:
                        mb = pi/numpy.max(q)
                    else:
                        mb = numpy.min(Bounds[Rvi:Rvi+2])
                    Rset[:, Rvi] = numpy.ones(Ncontrib)[:]*mb/2.
            else:
                Rset = Randfunc(Ncontrib)
        elif (size(Prior,0) != 0) & (size(Ncontrib) == 0):
            Ncontrib = size(Prior, 0)
            Rset = Prior
        elif size(Prior, 0) == Ncontrib:
            Rset = Prior
        elif size(Prior, 0) < Ncontrib:
            print "size of prior is smaller than Ncontrib. "\
                  "duplicating random prior values"
            # while size(Prior) < Nsph:
            Addi = numpy.random.randint(size(Prior,0),
                        size = Ncontrib - size(Prior,0))
            Rset = concatenate((Prior, Prior[Addi, :]))
            print "size now:", size(Rset)
        elif size(Prior, 0) > Ncontrib:
            print "Size of prior is larger than Ncontrib. "\
                  "removing random prior values"
            # remaining choices
            Remi = numpy.random.randint(size(Prior, 0), size = Ncontrib)
            Rset = Prior[Remi, :]
            print "size now:", size(Rset, 0)
        
        if Memsave == False:
            # calculate their form factors
            FFset = FFfunc(Rset)
            Vset = VOLfunc(Rset, Rpfactor)
            # Vset = (4.0/3*pi) * Rset**(3*Rpfactor)
            # calculate the intensities
            Iset = FFset**2 * (Vset + 0*FFset)**2 # a set of intensities
            Vst = sum(Vset**2) # total volume squared
            It = sum(Iset, 0) # the total intensity - eq. (1)
            It = reshape(It, (1, prod(shape(It)))) # reshaped to match I and q
        else:
            # calculate intensity in memory saving mode:
            # calculate volume for entire set, this does not take much space   
            Vset = VOLfunc(Rset, Rpfactor)

            FFset = FFfunc(Rset[0, :][newaxis, :])
            It = FFset**2 * (Vset[0] + 0*FFset)**2 # a set of intensities
            for ri in arange(1, Ncontrib):
                # calculate their form factors
                FFset = FFfunc(Rset[ri, :][newaxis, :])
                # a set of intensities
                It = It + FFset**2 * (Vset[ri] + 0*FFset)**2
            Vst = sum(Vset**2) # total volume squared
            It = reshape(It, (1, prod(shape(It)))) # reshaped to match I and q

        # Optimize the intensities and calculate convergence criterium
        # SMEAR function goes here
        It = SMEARfunc(It)
        Sci = numpy.max(I)/numpy.max(It) # init. guess for the scaling factor
        Bgi = numpy.min(I)
        Sc, Conval = self._Iopt(I, It/Vst, E, numpy.array([Sci, Bgi]),
                                ver = 1)
        # reoptimize with V2, there might be a slight discrepancy in the
        # residual definitions of V1 and V2 which would prevent optimization.
        Sc, Conval = self._Iopt(I, It/Vst, E, Sc)
        # print "Initial conval V1", Conval1
        print "Initial Chi-squared value", Conval

        if OutputIterations:
            # Output each iteration, starting with number 0. Iterations will
            # be stored in Details['Itersph'], Details['IterIfit'],
            # Details['IterConval'], Details['IterSc'] and
            # Details['IterPriorUnaccepted'] listing the unaccepted number of
            # moves before the recorded accepted move.

            # new iterations will (have to) be appended to this, cannot be
            # zero-padded due to size constraints
            Details['Itersph'] = Rset[:, newaxis]
            Details['IterIfit'] = (It/Vst*Sc[0] + Sc[1])[:, newaxis] # ibid.
            Details['IterConVal'] = Conval[newaxis]
            Details['IterSc'] = Sc[:, newaxis]
            Details['IterPriorUnaccepted'] = numpy.array(0)[newaxis]

        # start the MC procedure
        Now = time.time()
        Nmoves = 0 # tracking the number of moves
        Nnotaccepted = 0
        while (Conval > Convcrit) & (Niter < Maxiter):
            Rt = Randfunc()
            Ft = FFfunc(Rt)
            Vtt = VOLfunc(Rt, Rpfactor)
            Itt = (Ft**2 * Vtt**2)
            # Calculate new total intensity
            if Memsave == False:
                # we do subtractions and additions, which give us another
                # factor 2 improvement in speed over summation and is much
                # more scalable
                Itest = (It - Iset[Ri, :] + Itt)
            else:
                Fo = FFfunc(Rset[Ri, :][newaxis, :])
                Io = (Fo**2 * Vset[Ri]**2)
                Itest = (It - Io + Itt)

            # SMEAR function goes here
            Itest = SMEARfunc(Itest)
            Vstest = (sqrt(Vst) - Vset[Ri])**2 + Vtt**2
            # optimize intensity and calculate convergence criterium
            # using version two here for a >10 times speed improvement
            Sct, Convalt = self._Iopt(I, Itest/Vstest, E, Sc)
            # test if the radius change is an improvement:
            if Convalt < Conval: # it's better
                if Memsave:
                    Rset[Ri, :], It, Vset[Ri], Vst, Sc, Conval = \
                            (Rt, Itest, Vtt, Vstest, Sct, Convalt)
                else:
                    Rset[Ri,:], Iset[Ri,:], It, Vset[Ri], Vst, Sc, Conval = \
                            (Rt, Itt, Itest, Vtt, Vstest, Sct, Convalt)
                print "Improvement in iteration number {0}, "\
                      "Chi-squared value {1:f} of {2:f}\r".format(
                              Niter, Conval, Convcrit),
                Nmoves += 1
                if OutputIterations:
                    # output each iteration, starting with number 0. 
                    # Iterations will be stored in Details['Itersph'],
                    # Details['IterIfit'], Details['IterConval'],
                    # Details['IterSc'] and Details['IterPriorUnaccepted']
                    # listing the unaccepted number of moves before the
                    # recorded accepted move.

                    # new iterations will (have to) be appended to this,
                    # cannot be zero-padded due to size constraints
                    Details['Itersph'] = concatenate((Details['Itersph'],
                                                      Rset[:, :, newaxis]),
                                                      axis = 1)
                    Details['IterIfit'] = concatenate(
                            (Details['IterIfit'],
                             (Itest/Vstest*Sct[0] + Sct[1])[:, newaxis]),
                            axis=1) # ibid.
                    Details['IterConVal'] = concatenate(\
                            (Details['IterConVal'],
                             numpy.array(Convalt)[newaxis]))
                    Details['IterSc'] = concatenate((Details['IterSc'],
                                                     Sct[:,newaxis]), axis=1)
                    Details['IterPriorUnaccepted'] = concatenate(\
                            (Details['IterPriorUnaccepted'],
                             numpy.array(Nnotaccepted)[newaxis]))
                Nnotaccepted = -1
            # else nothing to do
            Ri += 1 # move to next sphere in list
            Ri = Ri % (Ncontrib) # loop if last sphere
            # number of non-accepted moves, resets to zero after accepted move
            Nnotaccepted += 1
            Niter += 1 # add one to the iteration number           
        if Niter >= Maxiter:
            print "exited due to max. number of iterations ({0}) "\
                  "reached".format(Niter)
        else:
            print "Normal exit"
        # the +0.001 seems necessary to prevent a divide by zero error
        # on some Windows systems.
        print "Number of iterations per second", \
                Niter/(time.time() - Now + 0.001)
        print "Number of valid moves", Nmoves
        print "final Chi-squared value %f" % (Conval)
        Details['Niter'] = Niter
        Details['Nmoves'] = Nmoves
        Details['elapsed'] = (time.time() - Now + 0.001)

        # Ifinal = sum(Iset, 0)/sum(Vset**2)
        Ifinal = It/sum(Vset**2)
        Ifinal = reshape(Ifinal, (1, prod(shape(Ifinal))))
        # SMEAR function goes here
        Ifinal = SMEARfunc(Ifinal)
        Sc, Conval = self._Iopt(I, Ifinal, E, Sc)    
        if OutputI:
            if OutputDetails:
                # DEBUG:
                # print 'Rset: {}, I: {}, Conval: {}'\
                # .format(shape(Rset),shape((Ifinal*Sc[0]+Sc[1])),
                #         shape(Conval))
                return Rset, (Ifinal * Sc[0] + Sc[1]), Conval, Details
            else:
                return Rset, (Ifinal * Sc[0] + Sc[1]), Conval
        else:
            # ifinal cannot be output with variable length intensity
            # outputs (in case of masked negative intensities or q limits)
            if OutputDetails:
                return Rset, Conval, Details
            else:
                return Rset, Conval

    #####################################################################
    #################### Post-optimisation Functions ####################
    #####################################################################

    def Histogram(self):
        """
        Takes the *Rrep* Result from the :py:meth:`McSAS.Analyse` function
        and calculates the corresponding volume- and number fractions for each
        contribution as well as the minimum observability limits. It will
        subsequently bin the Result across the range for histogramming purposes.

        While the volume-weighted distribution will be in absolute units
        (providing volume fractions of material within a given size range),
        the number distributions have been normalized to 1.
        
        Output a list of dictionaries with one dictionary per shape parameter:

            *VariableNumber*: int
                Shape parameter index. e.g. an ellipsoid has 3:
                width, height and orientation
            *Hx*: array
                Histogram bin left edge position (x-axis in histogram)
            *Hmid*: array
                Center positions for the size histogram bins
                (x-axis in histogram, used for errorbars)
            *Hwidth*: array
                Histogram bin width (x-axis in histogram,
                defines bar plot bar widths)
            *Hmean*: array
                Volume-weighted particle size distribution values for
                all *Nreps* Results (y-axis bar height)
            *Hnmean*: array
                Number-weighted analogue of the above *Hmean*
            *Hy*: size (Histbins x Nreps) array
                Volume-weighted particle size distribution bin values for each
                MC fit repetition (the mean of which is *Hmean*, and the sample
                standard deviation of which is *Hstd*)
            *Hny*: size (Histbins x Nreps) array
                Number-weighted particle size distribution bin values
                for each MC fit repetition
            *Hstd*: array
                Standard deviations of the corresponding volume-weighted size
                distribution bins, calculated from *Nreps* repetitions of the
                MCfit_sph() function
            *Hnstd*: array
                Standard deviation for the number-weigthed distribution
            *Vf*: size (Ncontrib x Nreps) array
                Volume fractions for each of Ncontrib contributions 
                in each of Nreps iterations
            *Nf*: size (Ncontrib x Nreps) array
                Number fraction for each contribution
            *Vft*: size (Nreps) array
                Total scatterer volume fraction for each of the *Nreps*
                iterations
            *Nft*: size (Nreps) array
                Total number fraction 
            *vfmin*: size (Nsph x Nreps) array
                minimum required volume fraction for each contribution to
                become statistically significant.
            *nfmin*: size (Nsph x Nreps) array
                number-weighted analogue to *vfmin*
            *vfminbins*: size (Hmid) array 
                array with the minimum required volume fraction per bin to
                become statistically significant. Used to display minimum
                required level in histogram.
            *nfminbins*: size (Hmid) array
                number-weighted analogue to *vfminbins*
            *Screps*: size (2 x Nreps) array
                Scaling and background values for each repetition. Used to
                display background level in data and fit plot.
        """
        # get settings
        # set the bin edges for our radius bins either based on a linear
        # division or on a logarithmic division of radii.
        Ncontrib = self.GetParameter('Ncontrib')
        Nreps = self.GetParameter('Nreps')
        Rpfactor = self.GetParameter('Rpfactor')
        Memsave = self.GetParameter('Memsave')
        drhosqr = self.GetParameter('drhosqr')
        Rrep = self.GetResult('Rrep')
        Histbins = self.GetParameter('Histbins')
        Histscale = self.GetParameter('Histscale')
        Bounds = self.GetParameter('Bounds')

        # ov = zeros(shape(Rrep)) # observability
        Vf = zeros((Ncontrib, Nreps)) # volume fraction for each contribution
        Nf = zeros((Ncontrib, Nreps)) # number fraction for each contribution
        qm = zeros((Ncontrib, Nreps)) # volume fraction for each contribution
        vfmin = zeros((Ncontrib, Nreps)) # volume frac. for each contribution
        nfmin = zeros((Ncontrib, Nreps)) # number frac. for each contribution
        Vft = zeros([Nreps]) # total volume fractions
        Nft = zeros([Nreps]) # total number 
        # Intensity scaling factors for matching to the experimental
        # scattering pattern (Amplitude A and flat background term b,
        # defined in the paper)
        Screps = zeros([2, Nreps])

        # Functions!
        Randfunc = self.GetFunction('RAND')
        FFfunc = self.GetFunction('FF')
        VOLfunc = self.GetFunction('VOL')
        SMEARfunc = self.GetFunction('SMEAR')

        # data!
        q = self.GetData('Q')
        I = self.GetData('I')
        E = self.GetData('IERR')

        # loop over each repetition
        for ri in range(Nreps):
            Rset = Rrep[:, :, ri] # the single set of R for this calculation
            # compensated volume for each sphere in the set
            Vset = VOLfunc(Rset, Rpfactor)
            if Memsave == False:
                # Form factors, all normalized to 1 at q=0.
                FFset = FFfunc(Rset)
                # Calculate the intensities
                # Intensity for each contribution as used in the MC calculation
                Iset = FFset**2 * (Vset + 0*FFset)**2
                It = sum(Iset, 0) # total intensity of the scattering pattern
            else:
                FFset = FFfunc(Rset[0, :][newaxis, :])
                It = FFset**2 * (Vset[0] + 0*FFset)**2 # a set of intensities
                for Rr in arange(1, Ncontrib):
                    # calculate their form factors
                    FFset = FFfunc(Rset[Rr, :][newaxis, :])
                    It = It + FFset**2 * (Vset[Rr] + 0*FFset)**2

            Vst = sum(Vset**2) # total compensated volume squared 
            It = reshape(It, (1, prod(shape(It))))
            It = SMEARfunc(It)
            
            # Now for each sphere, calculate its volume fraction
            # (p_c compensated):
            # compensated volume for each sphere in
            # the set Vsa = 4./3*pi*Rset**(3*Rpfactor)
            Vsa = VOLfunc(Rset, Rpfactor)
            # And the real particle volume:
            # compensated volume for each sphere in
            # the set Vsa = 4./3*pi*Rset**(3*Rpfactor)
            Vpa = VOLfunc(Rset, Rpfactor = 1.)
            # initial guess for the scaling factor.
            Sci = numpy.max(I) / numpy.max(It)
            Bgi = numpy.min(I)
            # optimize scaling and background for this repetition
            Sc, Cv = self._Iopt(I, It, E, [Sci, Bgi])
            Screps[:, ri] = Sc # scaling and background for this repetition.
            # a set of volume fractions
            Vf[:, ri] = (Sc[0] * Vsa**2/(Vpa * drhosqr)).flatten()
            Vft[ri] = sum(Vf[:, ri]) # total volume 
            Nf[:, ri] = Vf[:, ri]/(Vpa.flatten())
            Nft[ri] = sum(Nf[:, ri]) # total number
            for isi in range(Ncontrib): # For each sphere
                # calculate the observability (the maximum contribution for
                # that sphere to the total scattering pattern)
                # NOTE: no need to compensate for p_c here, we work with
                # volume fraction later which is compensated by default.
                # additionally, we actually do not use this value.
                # ov[isi,ri] = (Iset[isi,:]/(It)).max()
                if Memsave:
                    FFset = FFfunc(Rset[isi, :][newaxis, :])
                    Ir = FFset**2 * (Vset[isi] + 0 * FFset)**2
                    # determine where this maximum observability is
                    # of contribution isi (index)
                    qmi = numpy.argmax(Ir.flatten()/It.flatten())
                    # point where the contribution of isi is maximum
                    qm[isi, ri] = q[0, qmi]
                    vfmin[isi, ri] = numpy.min(E * Vf[isi, ri]/(Sc[0] * Ir))
                    nfmin[isi, ri] = vfmin[isi, ri]/Vpa[isi]
                else:
                    # determine where this maximum observability is
                    # of contribution isi (index)
                    qmi = numpy.argmax(Iset[isi, :].flatten()/It.flatten())
                    # point where the contribution of isi is maximum
                    qm[isi, ri] = q[0, qmi]
                    vfmin[isi, ri] = numpy.min(E * Vf[isi, ri]/
                                               (Sc[0] * Iset[isi, :]))
                    nfmin[isi, ri] = vfmin[isi, ri]/Vpa[isi]
                # close approximation:
                # vfmin[isi,ri] = (E[qmi]*Vf[isi,ri]/(Sc[0]*Iset[isi,qmi]))
                # or more precice but slower:
            Nf[:, ri] = Nf[:, ri]/Nft[ri]
            nfmin[:, ri] = nfmin[:, ri]/Nft[ri]

        # now we histogram over each variable
        # for each variable parameter we define,
        # we need to histogram separately.
        for vari in range(prod(shape(Histbins))):
            # Now bin whilst keeping track of which contribution ends up in
            # which bin: set bin edge locations
            if Histscale[vari] == 'lin':
                # Hx contains the Histbins+1 bin edges, or class limits.
                Hx = linspace(Bounds[0 + 2*vari],
                              Bounds[1 + 2*vari],
                              Histbins[vari] + 1)
            else:
                Hx = 10**(linspace(log10(Bounds[0 + 2*vari]),
                                   log10(Bounds[1 + 2*vari]),
                                   Histbins[vari] + 1))
            # total volume fraction contribution in a bin
            Hy = zeros([Histbins[vari], Nreps])
            # total number fraction contribution in a bin
            Hny = zeros([Histbins[vari], Nreps])
            # minimum required number of contributions /in a bin/ to make
            # a measurable impact
            vfminbin = zeros([Histbins[vari], Nreps])
            nfminbin = zeros([Histbins[vari], Nreps])
            Hmid = zeros(Histbins[vari])
            vfminbins = zeros(Histbins[vari])
            nfminbins = zeros(Histbins[vari])

            for ri in range(Nreps):
                # the single set of R for this calculation
                Rset = Rrep[:, vari, ri]
                for bini in range(Histbins[vari]):
                    # indexing which contributions fall into the radius bin
                    findi = ((Rset >= Hx[bini]) * (Rset < Hx[bini + 1]))
                    # print 'findi: {} Vf: {}'.format(shape(findi), shape(Vf))
                    # findi = findi[:, 0]
                    # y contains the volume fraction for that radius bin
                    Hy[bini, ri] = sum(Vf[findi, ri])
                    Hny[bini, ri] = sum(Nf[findi, ri])
                    if sum(findi) == 0:
                        vfminbin[bini, ri] = 0
                        nfminbin[bini, ri] = 0
                    else:
                        vfminbin[bini, ri] = numpy.max(vfmin[findi, ri])
                        vfminbin[bini, ri] = numpy.mean(vfmin[findi, ri])
                        nfminbin[bini, ri] = numpy.max(nfmin[findi, ri])
                        nfminbin[bini, ri] = numpy.mean(nfmin[findi, ri])
                    if isnan(Hy[bini, ri]):
                        Hy[bini, ri] = 0.
                        Hny[bini, ri] = 0.
            for bini in range(Histbins[vari]):
                Hmid[bini] = numpy.mean(Hx[bini:bini+2])
                vb = vfminbin[bini, :]
                vfminbins[bini] = numpy.max(vb[vb < inf])
                nb = nfminbin[bini, :]
                nfminbins[bini] = numpy.max(nb[vb < inf])
            Hmean = numpy.mean(Hy, axis=1)
            Hnmean = numpy.mean(Hny, axis=1)
            Hstd = numpy.std(Hy, axis=1)
            Hnstd = numpy.std(Hny, axis=1)
            self.SetResult(**{
                'VariableNumber': vari, # this line will place the Results in
                                        # the dict at self.Results[vari]
                'Hx': Hx,
                'Hmid': Hmid,
                'Hwidth': diff(Hx),
                'Hy': Hy,
                'Hny': Hny,
                'Hmean': Hmean,
                'Hstd': Hstd,
                'Hnmean': Hnmean,
                'Hnstd': Hnstd,
                'vfminbins': vfminbins,
                'vfmin': vfmin,
                'Vf': Vf,
                'Vft': Vft,
                'nfminbins': nfminbins,
                'nfmin': nfmin,
                'Nf': Nf,
                'Nft': Nft,
                'Screps': Screps})

    def GenerateTwoDIntensity(self):
        """
        This function is optionally run after the histogram procedure for
        anisotropic images, and will calculate the MC fit intensity in
        imageform
        """
        Result = self.GetResult()
        # load original Dataset
        q = self.GetData('Q', Dataset = 'original')
        I = self.GetData('I', Dataset = 'original')
        E = self.GetData('IERR', Dataset = 'original')
        PSI = self.GetData('PSI', Dataset = 'original')
        # we need to recalculate the Result in two dimensions
        kansas = shape(q) # we will return to this shape
        q = reshape(q, [1, -1]) # flatten
        I = reshape(I, [1, -1]) # flatten
        E = reshape(E, [1, -1]) # flatten
        PSI = reshape(PSI, [1, -1]) # flatten

        Randfunc = self.GetFunction('RAND')
        FFfunc = self.GetFunction('FF')
        VOLfunc = self.GetFunction('VOL')
        SMEARfunc = self.GetFunction('SMEAR')
        print "Recalculating final Result, this may take some time"
        # for each Result
        Iave = zeros(shape(q))
        Nreps = self.GetParameter('Nreps')
        Rpfactor = self.GetParameter('Rpfactor')
        qlims = self.GetParameter('qlims')
        psilims = self.GetParameter('psilims')
        Memsave = self.GetParameter('Memsave')
        Ncontrib = self.GetParameter('Ncontrib')
        Screps = self.GetResult('Screps')
        for nr in range(Nreps):
            print 'regenerating set {} of {}'.format(nr, Nreps)
            Rset = Result['Rrep'][:, :, nr]
            # calculate their form factors
            Vset = VOLfunc(Rset, Rpfactor)
            # Vset = (4.0/3*pi) * Rset**(3*Rpfactor)
            # calculate the intensities
            if Memsave == False:
                # Form factors, all normalized to 1 at q=0.
                FFset = FFfunc(Rset, Q = q, PSI = PSI)
                # Calculate the intensities
                # Intensity for each contribution as used in the MC calculation
                Iset = FFset**2 * (Vset + 0*FFset)**2
                # the total intensity of the scattering pattern
                It = sum(Iset, 0)
            else:
                FFset = FFfunc(Rset[0, :][newaxis, :], Q = q, PSI = PSI)
                It = FFset**2 * (Vset[0] + 0*FFset)**2 # a set of intensities
                for ri in arange(1, Ncontrib):
                    # calculate their form factors
                    FFset = FFfunc(Rset[ri, :][newaxis, :], Q = q, PSI = PSI)
                    # a set of intensities
                    It = It + FFset**2 * (Vset[ri] + 0*FFset)**2
            Vst = sum(Vset**2) # total volume squared
            It = reshape(It, (1, -1)) # reshaped to match I and q
            # Optimize the intensities and calculate convergence criterium
            # SMEAR function goes here
            It = SMEARfunc(It)
            Iave = Iave + It*Screps[0, nr] + Screps[1, nr] # add to average
        # print "Initial conval V1", Conval1
        Iave = Iave/Nreps
        # mask (lifted from ClipDataset)
        validbools = isfinite(q)
        # Optional masking of negative intensity
        if self.GetParameter('MaskNegI'):
            validbools = validbools * (I >= 0)
        if self.GetParameter('MaskZeroI'):
            validbools = validbools * (I != 0)
        if (qlims == []) and (psilims == []):
            # q limits not set, simply copy Dataset to FitData
            validbools = validbools
        if (not(qlims == [])): # and qlims is implicitly set
            # excluding the lower q limit may prevent q=0 from appearing
            validbools = validbools * \
                    (q > numpy.min(qlims)) & ( q<= numpy.max(qlims))
        # we assume here that we have a Dataset ['PSI']
        if (not(psilims == [])):
            # excluding the lower q limit may prevent q=0 from appearing
            validbools = validbools * \
                    (PSI > numpy.min(psilims)) & (PSI <= numpy.max(psilims))
        Iave = Iave * validbools
        # shape back to imageform
        I2D = reshape(Iave, kansas)
        self.SetResult(I2D = I2D)

    def ExportCSV(self, filename, *args, **kwargs):
        """
        This function writes a semicolon-separated csv file to [filename]
        containing an arbitrary number of output variables *\*args*. in case of
        variable length columns, empty fields will contain ''.

        Optional last argument is a keyword-value argument:
        VarableNumber=[integer], indicating which shape parameter it is
        intended to draw upon. VariableNumber can also be a list or array
        of integers, of the same length as the number of output variables
        *\*args* in which case each output variable is matched with a shape
        parameter index. Default is zero.

        Input arguments should be names of fields in *self.Result*.
        For example::

            A.McCSV('hist.csv', 'Hx', 'Hwidth', 'Hmean', 'Hstd',
                    VariableNumber = 0)

        I.e. just stick on as many columns as you'd like. They will be
        flattened by default. A header with the Result keyword names will be
        added.
        
        Existing files with the same filename will be overwritten by default.
        """
        vna = zeros(len(args), dtype = int)
        if 'VariableNumber' in kwargs:
            vni = kwargs['VariableNumber']
            if isinstance(vni, (list, ndarray)):
                if len(vni) != len(args):
                    print("Error in ExportCSV, supplied list of variablenumbers"
                          "does not have the length of 1 or the same length as"
                          "the list of output variables.")
                    return
                for vi in range(len(args)):
                    vna[vi] = vni[vi]
            else:
                # single integer value
                vna = vna + vni
                
        # uses sprintf rather than csv for flexibility
        ncol = len(args)
        # make format string used for every line, don't need this
        # linestr=''
        # for coli in range(ncol):
        #    linestr = linestr+'{'+'};'
        # strip the last semicolon, add a newline
        # linestr = linestr[0:-1]+'\n'

        inlist = list()
        for argi in range(len(args)):
            inlist.append(
                self.GetResult(args[argi],
                               VariableNumber = vna[argi]).flatten())
        # find out the longest row
        nrow = 0
        for argi in range(len(args)):
            nrow = numpy.max((nrow, len(inlist[argi])))
        # now we can open the file:
        fh = open(filename, 'w')
        emptyfields = 0
        # write header:
        linestr = ''
        for coli in range(ncol):
            linestr = linestr + '{};'.format(args[coli])
        linestr = linestr[0:-1] + '\n'
        fh.write(linestr)
        for rowi in range(nrow):
            linestr = ''
            for coli in range(ncol):
                # print 'rowi {} coli {} len(args[coli]) {}'
                # .format(rowi,coli,len(args[coli]))
                # we ran out of numbers for this arg
                if len(inlist[coli]) <= rowi:
                    linestr = linestr + ';' # add empty field
                    emptyfields += 1
                else:
                    linestr = linestr + '{};'.format(inlist[coli][rowi])
            linestr = linestr[0:-1] + '\n'

            fh.write(linestr)

        fh.close()
        print "{} lines written with {} columns per line, "\
              "and {} empty fields".format(rowi,ncol,emptyfields)

    def Plot(self, AxisMargin = 0.3):
        """
        This function plots the output of the Monte-Carlo procedure in two
        windows, with the left window the measured signal versus the fitted
        intensity (on double-log scale), and the righthand window the size
        distribution.
        """
        import matplotlib.font_manager as fm
        def SetAxis(ah):
            """Sets the axes Parameters. axtyp can be one of 'q' or 'R'"""
            import matplotlib.font_manager as fm
            plotfont = fm.FontProperties(
                        # this only works for macs, doesn't it?
                        # family = 'Courier New Bold',
                        # fname = '/Library/Fonts/Courier New Bold.ttf')
                        family = 'Arial')
            textfont = fm.FontProperties(
                        # Baskerville.ttc does not work when saving to eps
                        # family = 'Times New Roman',
                        # fname = '/Library/Fonts/Times New Roman.ttf')
                        family = 'Times')
            # SetAxis font and ticks
            ah.set_yticklabels(ah.get_yticks(), fontproperties = plotfont,
                               size = 'large')
            ah.set_xticklabels(ah.get_xticks(), fontproperties = plotfont,
                               size = 'large')
            ah.set_xlabel(ah.get_xlabel(), fontproperties = textfont,
                          size = 'x-large')
            ah.set_ylabel(ah.get_ylabel(), fontproperties = textfont,
                          size = 'x-large')
            # q_ax.set_yticklabels(q_ax.get_yticks(),
            #                      fontproperties = plotfont)
            # q_ax.set_xticklabels(q_ax.get_xticks(),
            #                      fontproperties = plotfont)
            # R_ax.spines['bottom'].set_color('black')
            ah.spines['bottom'].set_lw(2)
            ah.spines['top'].set_lw(2)
            ah.spines['left'].set_lw(2)
            ah.spines['right'].set_lw(2)
            ah.tick_params(axis = 'both', colors = 'black', width = 2,
                           which = 'major', direction = 'in', length = 6)
            ah.tick_params(axis = 'x', colors = 'black', width = 2,
                           which = 'minor', direction = 'in', length = 3)
            ah.tick_params(axis = 'y', colors = 'black', width = 2,
                           which = 'minor', direction = 'in', length = 3)
            # q_ax.spines['bottom'].set_lw(2)
            # q_ax.spines['top'].set_lw(2)
            # q_ax.spines['left'].set_lw(2)
            # q_ax.spines['right'].set_lw(2)
            # q_ax.tick_params(axis = 'both', colors='black',width=2,
            #                  which='major',direction='in',length=6)
            # q_ax.tick_params(axis = 'x', colors='black',width=2,
            #                  which='minor',direction='in',length=3)
            # q_ax.tick_params(axis = 'y', colors='black',width=2,
            #                  which='minor',direction='in',length=3)
            locs, labels = xticks()
            xticks(locs, map(lambda x: "%g" % x, locs))
            locs, labels = yticks()
            yticks(locs, map(lambda x: "%g" % x, locs))
            return ah

        # load Parameters
        Histscale = self.GetParameter('Histscale')
        Histweight = self.GetParameter('Histweight')
        # load Result
        Result = self.GetResult()
        # check how many Result plots we need to generate: maximum three.
        nhists = len(Histscale)

        # set plot font
        plotfont = fm.FontProperties(
                    size = 'large',
                    family = 'Arial')
        textfont = fm.FontProperties(
                    # Baskerville.ttc does not work when saving to eps
                    size = 'large',
                    family = 'Times')
        # initialize figure and axes
        fig = figure(figsize = (7*(nhists+1), 7), dpi = 80,
                     facecolor = 'w', edgecolor = 'k')
        # load original Dataset
        q = self.GetData('Q', Dataset = 'original')
        I = self.GetData('I', Dataset = 'original')
        E = self.GetData('IERR', Dataset = 'original')
        TwoDMode = False
        if ndim(q) > 1:
            # 2D data
            TwoDMode = True
            PSI = self.GetData('PSI', Dataset = 'original')
            # we need to recalculate the Result in two dimensions
            # done by GenerateTwoDIntensity function
            I2D = self.GetResult('I2D')
            Ishow = I.copy()
            # quadrant 1 and 4 are simulated data, 2 and 3 are measured data
            Ishow[(PSI >   0) * (PSI <=  90)] = I2D[(PSI >   0) * (PSI <=  90)]
            Ishow[(PSI > 180) * (PSI <= 270)] = I2D[(PSI > 180) * (PSI <= 270)]
            # xalimits=(-numpy.min(q[:,0]),numpy.max(q[:,-1]))
            # yalimits=(-numpy.min(q[0,:]),numpy.max(q[-1,:]))
            xmidi = int(round(size(q, 1)/2))
            ymidi = int(round(size(q, 0)/2))
            QX = numpy.array([-q[ymidi, 0], q[ymidi, -1]])
            QY = numpy.array([-q[0, xmidi], q[-1, xmidi]])
            extent = (QX[0], QX[1], QY[0], QY[1])

            q_ax = fig.add_subplot(1, (nhists+1), 1, axisbg = (.95, .95, .95),
                                   xlim = QX, ylim = QY, xlabel = 'q_x, 1/m',
                                   ylabel = 'q_y, 1_m')
            imshow(log10(Ishow), extent = extent, origin = 'lower')
            q_ax = SetAxis(q_ax)
            colorbar()
        else:
            q_ax = fig.add_subplot(1, (nhists+1), 1, axisbg = (.95, .95, .95),
                                   xlim = (numpy.min(q) * (1-AxisMargin),
                                           numpy.max(q) * (1+AxisMargin)),
                                   ylim = (numpy.min(I[I != 0]) * 
                                                          (1-AxisMargin),
                                           numpy.max(I) * (1+AxisMargin)),
                                   xscale = 'log', yscale = 'log',
                                   xlabel = 'q, 1/m', ylabel = 'I, 1/(m sr)')
            q_ax = SetAxis(q_ax)
            errorbar(q, I, E, zorder = 2, fmt = 'k.', ecolor = 'k',
                     elinewidth = 2, capsize = 4, ms = 5,
                     label = 'Measured intensity', lw = 2,
                     solid_capstyle = 'round', solid_joinstyle = 'miter')
            grid(lw = 2, color = 'black', alpha = .5, dashes = [1, 6],
                 dash_capstyle = 'round', zorder = -1)
            # xscale('log')
            # yscale('log')
            aq = sort(Result['Qfit'][0, :])
            aI = Result['Imean'][0, argsort(Result['Qfit'][0, :])]
            plot(aq, aI, 'r-', lw = 3, label = 'MC Fit intensity', zorder = 4)
            plot(aq, numpy.mean(Result['Screps'][1, :]) + 0*aq,
                 'g-', linewidth = 3,
                 label = 'MC Background level:\n\t ({0:03.3g})'
                         .format(numpy.mean(Result['Screps'][1, :])),
                 zorder = 3)
            leg = legend(loc = 1, fancybox = True, prop = textfont)
        title('Measured vs. Fitted intensity',
              fontproperties = textfont, size = 'x-large')
        R_ax = list()
        for histi in range(nhists):
            # get data:
            Hx = self.GetResult(parname = 'Hx',
                                VariableNumber = histi)
            Hmid = self.GetResult(parname = 'Hmid',
                                  VariableNumber = histi)
            Hwidth = self.GetResult(parname = 'Hwidth',
                                    VariableNumber = histi)
            if Histweight == 'volume':
                Hmean = self.GetResult(parname = 'Hmean',
                                       VariableNumber = histi)
                vfminbins = self.GetResult(parname = 'vfminbins',
                                           VariableNumber = histi)
                Hstd = self.GetResult(parname = 'Hstd',
                                      VariableNumber = histi)
            elif Histweight == 'number':
                Hmean = self.GetResult(parname = 'Hnmean',
                                       VariableNumber = histi)
                vfminbins = self.GetResult(parname = 'nfminbins',
                                           VariableNumber = histi)
                Hstd = self.GetResult(parname = 'Hnstd',
                                      VariableNumber = histi)
            else: 
                print "Incorrect value for Histweight: "\
                      "should be either 'volume' or 'number'"

            # prep axes
            if Histscale[histi] == 'log':
                # quick fix with the [0] reference. Needs fixing, this
                # plotting function should be rewritten to support multiple
                # variables.
                R_ax.append(fig.add_subplot(1, (nhists + 1), histi + 2,
                            axisbg = (.95, .95, .95),
                            xlim = (numpy.min(Hx) * (1 - AxisMargin),
                                    numpy.max(Hx) * (1 + AxisMargin)),
                            ylim = (0, numpy.max(Hmean) * (1 + AxisMargin)),
                            xlabel = 'Radius, m',
                            ylabel = '[Rel.] Volume Fraction',
                            xscale = 'log'))
            else:
                R_ax.append(fig.add_subplot(1, (nhists + 1), histi + 2,
                            axisbg = (.95, .95, .95),
                            xlim = (numpy.min(Hx) - 
                                        (1 - AxisMargin)*numpy.min(Hx),
                                    numpy.max(Hx) * (1 + AxisMargin)),
                            ylim = (0, numpy.max(Hmean) * (1 + AxisMargin)),
                            xlabel = 'Radius, m',
                            ylabel = '[Rel.] Volume Fraction'))

            R_ax[histi] = SetAxis(R_ax[histi])
            # fill axes
            bar(Hx[0:-1], Hmean, width = Hwidth, color = 'orange',
                edgecolor = 'black', linewidth = 1, zorder = 2,
                label = 'MC size histogram')
            plot(Hmid, vfminbins, 'ro', ms = 5, markeredgecolor = 'r',
                 label = 'Minimum visibility limit', zorder = 3)
            errorbar(Hmid, Hmean, Hstd, zorder = 4, fmt = 'k.', ecolor = 'k',
                     elinewidth = 2, capsize = 4, ms = 0, lw = 2,
                     solid_capstyle = 'round', solid_joinstyle = 'miter')
            legend(loc = 1, fancybox = True, prop = textfont)
            title('Radius size histogram', fontproperties = textfont,
                  size = 'x-large')
            # reapply limits in x
            xlim((numpy.min(Hx) * (1 - AxisMargin),
                  numpy.max(Hx) * (1 + AxisMargin)))

        fig.subplots_adjust(left = 0.1, bottom = 0.11,
                            right = 0.96, top = 0.95,
                            wspace = 0.23, hspace = 0.13)
        
    def RangeInfo(self, ParameterRange = [0, inf], Parameter = 0):
        """Calculates the total volume or number fraction of the MC Result
        within a given range, and returns the total numer or volume fraction
        and its standard deviation over all nreps as well as the first four
        distribution moments: mean, variance, skewness and kurtosis
        (Pearson's definition).
        Will use the *Histweight* parameter for determining whether to return
        the volume or number-weighted values.

        Input arguments are:

            *ParameterRange*
              The radius range in which the moments are to be calculated
            *Parameter*
              Which shape parameter the moments are to be calculated for
              (e.g. 0 = width, 1 = length, 2 = orientation)

        Returns a 4-by-2 array, with the values and their sample standard
        deviations over all *Nreps*.
        """
        Rrep = self.GetResult('Rrep')
        Ncontrib = size(Rrep, 0)
        NRval = size(Rrep, 1)
        Nreps = size(Rrep, 2)
        Rpfactor = self.GetParameter('Rpfactor')
        Memsave = self.GetParameter('Memsave')
        drhosqr = self.GetParameter('drhosqr')
        Histbins = self.GetParameter('Histbins')
        Histscale = self.GetParameter('Histscale')
        Histweight = self.GetParameter('Histweight')
        Bounds = self.GetParameter('Bounds')
        
        # ov = zeros(shape(Rrep)) # observability
        Vf = self.GetResult('Vf') # volume fraction for each contribution
        Nf = self.GetResult('Nf') # number fraction for each contribution
        Vft = self.GetResult('Vft') # total volume fractions
        Nft = self.GetResult('Nft') # total number 
        # Intensity scaling factors for matching to the experimental
        # scattering pattern (Amplitude A and flat background term b,
        # defined in the paper)
        Screps = self.GetResult('Screps')

        Val = zeros(Nreps) # total value
        Mu = zeros(Nreps) # moments..
        Var = zeros(Nreps) # moments..
        Skw = zeros(Nreps) # moments..
        Krt = zeros(Nreps) # moments..

        # loop over each repetition
        for ri in range(Nreps):
            # the single set of R for this calculation
            Rset = Rrep[:, Parameter, ri]
            validi = (Rset > numpy.min(ParameterRange)) * \
                     (Rset < numpy.max(ParameterRange))
            Rset = Rset[validi]
            # compensated volume for each sphere in the set
            Vset = Vf[validi, ri]
            Nset = Nf[validi, ri]

            if Histweight == 'volume':
                Val[ri] = sum(Vset)
                Mu[ri] = sum(Rset * Vset)/sum(Vset)
                Var[ri] = sum( (Rset - Mu[ri])**2 * Vset )/sum(Vset)
                sigma = sqrt(abs(Var[ri]))
                Skw[ri] = sum( (Rset-Mu[ri])**3 * Vset )/ \
                          (sum(Vset) * sigma**3)
                Krt[ri] = sum( (Rset-Mu[ri])**4 * Vset )/ \
                          (sum(Vset) * sigma**4)
            elif Histweight == 'number':
                Val[ri] = sum(Nset)
                Mu[ri] = sum(Rset * Nset)/sum(Nset)
                Var[ri] = sum( (Rset-Mu[ri])**2 * Nset )/sum(Nset)
                sigma=sqrt(abs(Var[ri]))
                Skw[ri] = sum( (Rset-Mu[ri])**3 * Nset )/ \
                          (sum(Nset) * sigma**3)
                Krt[ri] = sum( (Rset-Mu[ri])**4 * Nset )/ \
                          (sum(Nset) * sigma**4)
            else:
                print("Error in moment calculation, "
                      "unrecognised Histweight value")
                return None

        return numpy.array([[numpy.mean(Val), numpy.std(Val, ddof=1)],
                            [numpy.mean(Mu), numpy.std(Mu, ddof=1)],
                            [numpy.mean(Var), numpy.std(Var, ddof=1)],
                            [numpy.mean(Skw), numpy.std(Skw, ddof=1)],
                            [numpy.mean(Krt), numpy.std(Krt, ddof=1)]])
        

########################## END McSAS OBJECT ############################

#some quick pickle Functions to make my life easier

def pickle_read(filename):
    """*\*args* can be 1-4, indicates number of output variables.
    If it is even possible to extract more from pickle."""
    fh = open(filename)
    O = pickle.load(fh)
    fh.close()
    return O

def pickle_write(filename, DBlock):
    """Writes DBlock to a file."""
    fh = open(filename, 'w')
    pickle.dump(DBlock, fh)
    fh.close()
    return

def binning_array(Q, PSI, I, IERR, S = 2):
    """This function applies a simple S-by-S binning routine on images.
    It calculates new error based on old error superseded by standard
    deviation in a bin."""
    def isodd(x):
        #checks if a value is even or odd
        return bool(x & 1)
    ddi = {'Q': Q, 'PSI': PSI, 'I': I, 'IERR':IERR}
    
    sq = shape(Q)
    if isodd(sq[0]):
        # trim edge
        for it in ddi.keys():
            ddi[it] = ddi[it][1:, :]
    if isodd(sq[1]):
        # trim edge
        for it in ddi.keys():
            ddi[it] = ddi[it][:, 1:]
    # now we can do n-by-n binning
    sq = shape(Q)
    qo = zeros((sq[0]/S, sq[1]/S))
    ddo = {'Q': qo.copy(), 'PSI': qo.copy(),
           'I': qo.copy(), 'IERR': qo.copy()}
    for it in ['Q', 'PSI', 'I']:
        for ri in range(sq[0]/S):
            for ci in range(sq[1]/S):
                ddo[it][ri, ci] = numpy.mean(
                        ddi[it][S*ri:(S*ri+S), S*ci:(S*ci+S)])
        
    for ri in range(sq[0]/S):
        for ci in range(sq[1]/S):
            meanE = sqrt(sum((
                        ddi['IERR'][S*ri:(S*ri+S), S*ci:(S*ci+S)])**2
                    ))/S**2
            # sample standard deviation
            stdI = numpy.std(ddi['I'][S*ri:(S*ri+S), S*ci:(S*ci+S)])
            # stdI=0
            ddo['IERR'][ri, ci] = numpy.max((meanE, stdI))
    return ddo

def binning_1D(q, I, E = [], Nbins = 200, Stats = 'STD'):
    """An unweighted binning routine.
    The intensities are sorted across bins of equal size.
    If error provided is empty, the standard deviation of the intensities in
    the bins are computed."""
    # Let's make sure the input is consistent
    if size(q) != size(I):
        print "Incompatible sizes of q and I"
        return
    elif (size(E) != 0) & (size(E) != size(I)):
        print "Size of E is not identical to q and I"
        return

    #flatten q, I and E
    q = reshape(q, size(q), 0)
    I = reshape(I, size(I), 0)
    E = reshape(E, size(E), 0)

    # define the bin edges and centres, and find out the stepsize while
    # we're at it. Probably, there is no need for knowing the edges...
    qbin_edges = linspace(numpy.min(q), numpy.max(q), Nbins + 1)
    stepsize = qbin_edges[1] - qbin_edges[0]
    qbin_centres = linspace(numpy.min(q) + 0.5*stepsize,
                            numpy.max(q) - 0.5*stepsize, Nbins)
    
    # sort q, let I and E follow sort
    sort_ind = numpy.argsort(q, axis = None)
    q = q[sort_ind]
    I = I[sort_ind]
    Ibin = numpy.zeros(Nbins)
    Ebin = numpy.zeros(Nbins)    
    SDbin = numpy.zeros(Nbins)    
    SEbin = numpy.zeros(Nbins)    
    if (size(E) != 0):
        E = E[sort_ind]

    # now we can fill the bins
    for Bini in range(Nbins):
        # limit ourselves to only the bits we're interested in:
        lim_bool_array = ((q  > (qbin_centres[Bini] - stepsize)) &
                          (q <= (qbin_centres[Bini] + stepsize)))
        I_to_bin = I[lim_bool_array]
        if (size(E) != 0):
            E_to_bin = sum(E[lim_bool_array])

        # find out the weighting factors for each q,I,E-pair in the array  
        weight_fact = ones(size(I_to_bin))

        # sum the intensities in one bin and normalize by number of pixels
        Ibin[Bini] = sum(I_to_bin)/sum(weight_fact)

        # now we deal with the Errors:
        if (size(E) != 0):
            # if we have errors supplied from outside
            # standard error calculation:
            SEbin[Bini] = sqrt(sum(E_to_bin**2 * weight_fact))/ \
                            sum(weight_fact)
            # Ebin2[Bini] = sqrt(sum((E_to_bin*weight_fact)**2))/ \
            #               sum(weight_fact) old, incorrect
            if Stats == 'auto':
                # according to the definition of sample-standard deviation
                SDbin[Bini] = sqrt(sum((
                                I_to_bin - Ibin[Bini])**2 * weight_fact
                                   )/(sum(weight_fact) - 1))
                # maximum between standard error and Poisson statistics
                SEbin[Bini] = numpy.max(
                        array([SEbin[Bini],
                               SDbin[Bini]/sqrt(sum(weight_fact))]))
        else:           
            # calculate the standard deviation of the intensity in the bin
            # both for samples with supplied error as well as for those where
            # the error is supposed to be calculated
            # according to the definition of sample-standard deviation
            SDbin[Bini] = sqrt(sum(
                                (I_to_bin-Ibin[Bini])**2 * weight_fact
                                )/(sum(weight_fact) - 1))
            # calculate standard error by dividing the standard error by the
            # square root of the number of measurements
            SEbin[Bini] = SDbin[Bini]/sqrt(sum(weight_fact))

    return qbin_centres, Ibin, SEbin

def binning_weighted_1D(q, I, E = [], Nbins = 200, Stats = 'SE'):
    """Implementation of the binning routine written in Matlab.
    The intensities are divided across the q-range in bins of equal size.
    The intensities of a pixel are divided between the two neighbouring bins
    depending on the distances to the centres. If error provided is empty,
    the standard deviation of the intensities in the bins are computed.

    **Usage**::

        qbin, Ibin, Ebin = binning_weighted_1D(q, I, E = [],
                                               Nbins = 200, Stats = 'SE')

    **Optional input arguments**:

    *Nbins*: integer indicating the number of bins to divide the intensity
        over. Alternatively, this can be an array of equidistant bin centres.
        If you go this route, depending on the range, not all intensity may be
        counted.
    *Stats*: Can be set to 'auto'. This takes the maximum error between
        supplied Poisson statistics error-based errors or the standard error.

    Written by Brian R. Pauw, 2011, released under BSD open source license.
    """
    # let's make sure the input is consistent
    if size(q) != size(I):
        print "Incompatible lengths of q and I, "\
              "q must be of the same number of elements as I"
        return
    elif (size(E) != 0) & (size(E) != size(I)):
        print "Size of E is not identical to q and I"
        return
    if (Stats.lower() != 'std') & (Stats.lower() != 'poisson') & \
       (Stats.lower() != 'se') & (Stats.lower() != 'auto'):
        print "Statistics can only be set to 'SE' (default), or 'auto'.\n"
        print "Only use 'auto' for photon-counting detectors, selects "\
              "largest error between SE and Poisson.\n"
        print "If errors are supplied, standard errors are not calculated "\
              "except in the case of 'auto'"
        return
    if (size(Nbins) == 1):
        if (Nbins < 1):
            print "number of bins, Nbins, is smaller than one. "\
                  "I need at least one bin to fill"
            return
    if size(Nbins) > 1:
        print "Nbins is larger than one value. Assuming that an equidistant "\
              "list of bin centres has been supplied"

    # flatten q, I and E
    q = reshape(q, size(q), 0)
    I = reshape(I, size(I), 0)
    E = reshape(E, size(E), 0)
    
    if size(Nbins) == 1:
        # define the bin edges and centres, and find out the stepsize while
        # we're at it. Probably, there is no need for knowing the edges...
        # do not use qbin_edges!
        qbin_edges, stepsize = linspace(numpy.min(q), numpy.max(q),
                                        Nbins + 1, retstep = True)
        # stepsize = qbin_edges[1] - qbin_edges[0]
        qbin_centres = linspace(numpy.min(q) + 0.5*stepsize,
                                numpy.max(q) - 0.5*stepsize, Nbins)
    else:
        if (numpy.min(q) > numpy.max(Nbins)) | \
           (numpy.max(q) < numpy.min(Nbins)):
            print "Bin centres supplied do not overlap with the q-range, "\
                  "cannot continue"
            return
        qbin_centres = sort(Nbins)
        stepsize = mean(diff(qbin_centres))
        Nbins = size(qbin_centres)

    # initialize output matrices
    Ibin = numpy.zeros(Nbins)
    SDbin = numpy.zeros(Nbins)    
    SEbin = numpy.zeros(Nbins)    

    # now we can fill the bins
    for Bini in range(Nbins):
        # limit ourselves to only the bits we're interested in:
        lim_bool_array = ((q  > (qbin_centres[Bini] - stepsize)) & \
                          (q <= (qbin_centres[Bini] + stepsize)))
        q_to_bin = q[lim_bool_array]
        I_to_bin = I[lim_bool_array]
        if (size(E) != 0):
            E_to_bin = E[lim_bool_array]

        # find out the weighting factors for each q,I,E-pair in the array
        q_dist = abs(q_to_bin - qbin_centres[Bini])
        weight_fact = (1 - q_dist/stepsize)

        # sum the intensities in one bin
        Ibin[Bini] = sum(I_to_bin * weight_fact)/sum(weight_fact)

        # now we deal with the Errors:
        if (size(E) != 0): # if we have errors supplied from outside
            # standard error calculation:
            SEbin[Bini] = sqrt(sum(E_to_bin**2 * weight_fact))/sum(weight_fact)
            # Ebin2[Bini] = sqrt(sum((E_to_bin * weight_fact)**2))/
            #                       sum(weight_fact) old, incorrect
            if Stats == 'auto':
                # according to the definition of sample-standard deviation
                SDbin[Bini] = sqrt(sum(
                    (I_to_bin - Ibin[Bini])**2 * weight_fact
                                    )/(sum(weight_fact) - 1))
                # maximum between standard error and Poisson statistics
                SEbin[Bini] = numpy.max(array([
                                        SEbin[Bini],
                                        SDbin[Bini] / sqrt(sum(weight_fact))]))
        else:           
            # calculate the standard deviation of the intensity in the bin
            # both for samples with supplied error as well as for those where
            # the error is supposed to be calculated
            # according to the definition of sample-standard deviation
            SDbin[Bini] = sqrt(sum(
                        (I_to_bin - Ibin[Bini])**2 * weight_fact
                                )/(sum(weight_fact)-1))
            # calculate standard error by dividing the standard error by the
            # square root of the number of measurements
            SEbin[Bini] = SDbin[Bini]/sqrt(sum(weight_fact))
    return qbin_centres, Ibin, SEbin
 
##general Functions
#def csqr(Sc,I,Ic,E):
#    """Least-squares error for use with scipy.optimize.leastsq"""
#    cs=(I-Sc[0]*Ic-Sc[1])/E
#    #print "Size E",size(E)
#    #print "Sc: %f, %f" %(Sc[0],Sc[1])
#    return cs
#
#def Iopt(I,Ic,E,Sc,OutputI=False):
#    """Optimizes the scaling and background factor to match Ic closest to I.
#    Returns an array with scaling factors. Input Sc has to be a two-element
#    array with the scaling and background.
#
#    New version, using leastsq and csqr, speed improvement of over
#    a factor of 10 w.r.t. V1's use in the MC algorithm
#    """
#    # initial guesses. No bounds at the moment are applied,
#    # except that the intensity scaling has to be positive.
#    Sc,success=scipy.optimize.leastsq(csqr,Sc,args=(I.flatten(),Ic.flatten(),
#                                      E.flatten()),full_output=0)
#    #print "Sc: %f, %f" %(Sc[0],Sc[1])
#    cval=csqr_v1(I,Sc[0]*Ic+Sc[1],E)
#    if OutputI:
#        return Sc,cval,Sc[0]*Ic+Sc[1]
#    else:
#        return Sc,cval
#
#def csqr_v1(I,Ic,E):
#    """Least-squares for data with known error,
#    size of parameter-space not taken into account."""
#    cs=sum(((I-Ic)/E)**2)/(size(I))
#    return cs
#
#def Iopt_v1(I,Ic,E,Sc,OutputI=False,Background=True):
#    """Optimizes the scaling and background factor to match Ic closest to I.
#    Returns an array with scaling factors. Input Sc has to be a two-element
#    array with the scaling and background.
#
#    Old version, using fmin and csqr_v1.
#    """
#    # initial guesses. No bounds at the moment are applied,
#    # except that the intensity scaling has to be positive.
#    # Background can be set to False to just find the scaling factor.
#    if Background:
#        Sc=scipy.optimize.fmin(lambda Sc: 
#                   csqr_v1(I,Sc[0]*Ic+Sc[1],E),Sc,full_output=0, disp=0)
#        cval=csqr_v1(I,Sc[0]*Ic+Sc[1],E)
#    else:
#        Sc[1]=0.
#        Sc=scipy.optimize.fmin(lambda Sc:
#                   csqr_v1(I,Sc[0]*Ic,E),Sc,full_output=0, disp=0)
#        Sc[1]=0.
#        cval=csqr_v1(I,Sc[0]*Ic,E)
#    if OutputI:
#        return Sc,cval,Sc[0]*Ic+Sc[1]
#    else:
#        return Sc,cval

# vim: set ts=4 sts=4 sw=4 tw=0:
