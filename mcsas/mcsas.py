# -*- coding: utf-8 -*-
# mcsas/mcsas.py
# Find the reST syntax at http://sphinx-doc.org/rest.html

import numpy # For arrays
from numpy import (inf, array, reshape, shape, pi, diff, zeros,
                  size, sum, sqrt, log10,
                  isnan, newaxis)
from scipy import optimize
import time # Timekeeping and timing of objects
import sys # For printing of slightly more advanced messages to stdout
import logging
logging.basicConfig(level = logging.INFO)

from cutesnake.utils import isList, isFrozen
from cutesnake.dataset import DataSet
from cutesnake.utils import isList, isString, isFrozen
from cutesnake.algorithm import (AlgorithmBase,
                                 RandomUniform, RandomExponential)
from utils.parameter import (Parameter, FitParameterBase)
from utils.propertynames import PropertyNames
from models.scatteringmodel import ScatteringModel
from models.sphere import Sphere
from cutesnake.utilsgui import processEventLoop

from plotting import plotResults
from sasdata import SASData
from mcsasparameters import McSASParameters

class McSAS(AlgorithmBase):
    r"""
    Main class containing all functions required to do Monte Carlo fitting.

    **Required input Parameters:**

        - *Q*: 1D or 2D array of q-values
        - *I*: corresponding intensity values of the same shape
        - *IError*: corresponding intensity uncertainties of the same shape
        - *model*: The scattering model object to assume.
                   It has to be an instance of :py:class:`ScatteringModel`.

    **Optional input Parameters:**

        - *Psi*: 2D array
            Detector angle values, only required for 2D pattern fitting.
        - *contribParamBounds*: list
            Two-element vector or list indicating upper and lower size
            bounds of the particle radii used in the fitting procedure. If
            not provided, these will be estimated as:
            :math:`R_{max} = {pi \over q_{min}}` and
            :math:`R_{min} = {pi \over q_{max}}`. Units in meter.
        - *numContribs*: int, default: 200
            Number of spheres used for the MC simulation
        - *maxIterations*: int, default: 1e5
            Maximum number of iterations for the :py:func:`MCFit` function
        - *compensationExponent*: float, default: :math:`1.5 \over 3`
            Parameter used to compensate the :math:`volume^2` scaling of each
            sphere contribution to the simulated I(q).
        - *numReps*: int, default: 100
            Number of repetitions of the MC fit for determination of final
            histogram uncertainty.
        - qBounds*: list, default: [0, inf]
            Limits on the fitting range in q.
            Units in :math:`m^{-1}`
        - *histogramBins*: int, default: 50
            Number of bins used for the histogramming procedure.
        - *histogramXScale*: string, default: 'log'
            Can be set to 'log' for histogramming on a logarithmic size scale,
            recommended for q- and/or size-ranges spanning more than a decade.
        - *histogramWeighting*: string, default: 'volume'
            Can be set to 'number' to force plotting of number-weighted
            distributions
        - *deltaRhoSquared*: float, default: 1
            Scattering contrast - when known it will be used to calculate the
            absolute volume fraction of each contribution.
            Units in :math:`m^{-4}`
        - *convergenceCriterion*: float, default: 1
            Convergence criterion for the least-squares fit. The fit converges
            once the :math:`normalized \chi^2 < convergenceCriterion`. If
            convergence is reached with `convergenceCriterion == 1`, the model
            describes the data (on average) to within the uncertainty, and thus
            all information has been extracted from the scattering pattern.
        - *startFromMinimum*: bool, default: False
            If set to False, the starting configuration is a set of spheres
            with radii uniformly sampled between the given or estimated
            bounds. If set to True, the starting configuration is a set of
            spheres with radii set to the lower given or estimated Bound
            (if not zero). Practically, this makes little difference and this
            feature might be depreciated.
        - *maxRetries*: int, default: 5
            If a single MC optimization fails to reach convergence within
            *maxIterations*, it may just be due to bad luck. The procedure
            will try to redo that MC optimization for a maximum of
            *maxRetries* tries before concluding that it is not bad luck
            but bad input.
        - *doPlot*: Bool, default: False
            If set to True, will generate a plot showing the data and fit, as
            well as the Resulting size histogram.

    **Returns:**

    A McSAS object with the following Results stored in the *result* member
    attribute. These can be extracted using
    McSAS.result[<parameterIndexNumber>]['<Keyword>']
    where the *parameterIndexNumber* indicates which shape parameter 
    information is requested.
    E.g. an ellipsoid has 3: width, height and orientation.
    (Some information is only stored in *parameterIndexNumber = 0* (default)).

    **Keyword** may be one of the following:

        *fitIntensityMean*: 1D array (*common result*)
            The fitted intensity, given as the mean of all numReps Results.
        *fitQ*: 1D array (*common result*)
            Corresponding q values
            (may be different than the input q if *QBounds* was used).
        *fitIntensityStd*: array (*common result*)
            Standard deviation of the fitted I(q), calculated as the standard 
            deviation of all numReps results.
        *contribs*: size array (numContribs x numReps) (*common result*)
            Collection of numContribs contributions fitted to best represent 
            the provided I(q) data. Contains the Results of each of 
            *numReps* iterations. This can be used for rebinning without 
            having to re-optimize.
        *scalingFactors*: size array (2 x numReps) (*common result*)
            Scaling and background values for each repetition.
            Used to display background level in data and fit plot.
        *histogramXLowerEdge*: array
            histogram bin left edge position (x-axis in histogram).
        *histogramXMean*: array
            Center positions for the size histogram bins
            (x-axis in histogram, used for errorbars).
        *histogramXWidth*: array
            histogram bin width
            (x-axis in histogram, defines bar plot bar widths).
        *volumeHistogramYMean*: array
            Volume-weighted particle size distribution values for
            all numReps Results (y-axis bar height).
        *numberHistogramYMean*: array
            Number-weighted analogue of the above *volumeHistogramYMean*.
        *volumeHistogramRepetitionsY*: size array (McSASParameters.histogramBins x numReps)
            Volume-weighted particle size distribution bin values for
            each fit repetition (the mean of which is *volumeHistogramYMean*, 
            and the sample standard deviation is *volumeHistogramYStd*).
        *numberHistogramRepetitionsY*: size array (McSASParameters.histogramBins x numReps)
            Number-weighted particle size distribution bin values for
            each MC fit repetition.
        *volumeHistogramYStd*: array
            Standard deviations of the corresponding volume-weighted size
            distribution bins, calculated from *numReps* repetitions of the
            model fitting function.
        *numberHistogramYStd*: array
            Standard deviation for the number-weigthed distribution.
        *volumeFraction*: size array (numContribs x numReps)
            Volume fractions for each of numContribs contributions in each of
            *numReps* iterations.
        *numberFraction*: size array (numContribs x numReps)
            Number fraction for each contribution.
        *totalVolumeFraction*: size array (numReps)
            Total scatterer volume fraction for each of the *numReps* 
            iterations.
        *totalNumberFraction*: size array (numReps)
            Total number fraction.
        *minimumRequiredVolume*: size array (numContribs x numReps)
            Minimum required volume fraction for each contribution to become
            statistically significant.
        *minimumRequiredNumber*: size array (numContribs x numReps)
            Number-weighted analogue to *minimumRequiredVolume*.
        *volumeHistogramMinimumRequired*: size array (histogramXMean)
            Array with the minimum required volume fraction per bin to become
            statistically significant. Used to display minimum required level
            in histogram.
        *numberHistogramMinimumRequired*: size array (histogramXMean)
            Number-weighted analogue to *volumeHistogramMinimumRequired*.
        *scalingFactors*: size array (2 x numReps)
            Scaling and background values for each repetition. Used to display
            background level in data and fit plot.
        *totalVolumeFraction*: size array (numReps)
            Total scatterer volume fraction for each of the *numReps*
            iterations.
        *minimumRequiredVolume*: size array (numContribs x numReps)
            Minimum required volube fraction for each contribution to become
            statistically significant.
        *volumeHistogramMinimumRequired*: size array (histogramXMean)
            Array with the minimum required volume fraction per bin to become
            statistically significant. Used to display minimum required level
            in histogram.

    **Internal Variables**
    
    :py:attr:`self.Dataset`
        Where Q, Psi, I and IError is stored, original Dataset.
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

    """

    dataset = None # user provided data to work with
    model = None
    result = None
    shortName = "McSAS"
    parameters = (Parameter("numContribs", 200,
                    displayName = "number of contributions",
                    valueRange = (1, 1e6)),
                  Parameter("numReps", 100,
                    displayName = "number of repetitions",
                    valueRange = (1, 1e6)),
                  Parameter("maxIterations", 1e5,
                    displayName = "maximum iterations",
                    valueRange = (1, 1e100)),
                  Parameter("histogramBins", 50,
                    displayName = "number of histogram bins",
                    valueRange = (1, 1e6)),
                  Parameter("convergenceCriterion", 1.0,
                    displayName = "convergence criterion",
                    valueRange = (0., numpy.inf)),
                  Parameter("findBackground", True,
                    displayName = "find background level?"),
    )
    figureTitle = None # FIXME: put this elsewhere, works for now
                       # set to output file name incl. timestamp, atm


    def __init__(self, **kwargs):
        """
        The constructor, takes keyword-value input Parameters. They can be
        one of the aforementioned parameter keyword-value pairs.
        This does the following:

            1. Initialises the variables to the right type
            2. Parses the input
            3. Stores the supplied data twice, one original and one for fitting
                (the latter of which may be clipped or otherwise adjusted)
            4. Applies Q- and optional Psi- limits to the data
            5. Reshapes FitData to 1-by-n dimensions
            6. Sets the function references
            7. Calculates the shape parameter bounds if not supplied
            8. Peforms simple checks on validity of input
            9. Runs the analyse() function which applies the MC fit multiple
               times
            10. Runs the histogram() procedure which processes the MC result
            11. Optionally recalculates the resulting intensity in the same
                shape as the original (for 2D Datasets)
            12. Optionally displays the results graphically.

        .. document private Functions
        .. automethod:: optimScalingAndBackground
        """
        AlgorithmBase.__init__(self)

    def calc(self, **kwargs):
        # initialize
        self.result = [] # TODO
        self.stop = False # TODO, move this into some simple result structure, eventually?
        # set data values
        self.setData(kwargs)
        # set supplied kwargs and passing on
        self.setParameter(kwargs)
        # apply q and psi limits and populate self.FitData
        self.dataset.clip(McSASParameters.qBounds,
                          McSASParameters.psiBounds,
                          McSASParameters.maskNegativeInt,
                          McSASParameters.maskZeroInt)
        if (McSASParameters.model is None or
            not isinstance(McSASParameters.model, ScatteringModel)):
            McSASParameters.model = Sphere() # create instance
            logging.info("Default model not provided, setting to: {0}"
                    .format(str(McSASParameters.model.name())))
        if self.model is None:
            self.model = McSASParameters.model
        logging.info("Using model: {0}".format(str(self.model.name())))
        if not self.model.paramCount():
            logging.warning("No parameters to analyse given! Breaking up.")
            return
        logging.info(
                "\n".join(["Analysing parameters: "]+
                    [str(p)+", active: "+str(p.isActive())
                        for p in self.model.params()])
        )
        self.checkParameters() # checks histbins
                               # (-> should go into custom parameter type)
        self.analyse()
        # continue if there are results only
        if not len(self.result):
            return
        self.histogram()

        if self.dataset.is2d:
            # 2D mode, regenerate intensity
            # TODO: test 2D mode
            self.gen2DIntensity()

        if McSASParameters.doPlot:
            self.plot()

    def setData(self, kwargs):
        """Sets the supplied data in the proper location. Optional argument
        *Dataset* can be set to ``fit`` or ``original`` to define which
        Dataset is set. Default is ``original``.
        """
        isOriginal = True
        try:
            kind = kwargs['Dataset'].lower()
            if kind not in ('fit', 'original'):
                raise ValueError
            if kind == 'fit':
                isOriginal = False
        except:
            pass
        # expecting flat arrays, TODO: check this earlier
        data = tuple((kwargs.pop(n, None) for n in ('Q', 'I', 'IError', 'Psi')))
        if data[0] is None:
            raise ValueError("No q values provided!")
        if data[1] is None:
            raise ValueError("No intensity values provided!")
        if data[2] is None:
            # ValueError instead? Is it mandatory to have IError?
            logging.warning("No intensity uncertainties provided!")
            # TODO: generate some
            #B: nope. It is up to the user to supply error estimates. these
            #B: are essential to good data practices.
            #B: i.e. Make it easy, but not so easy it encourages "abuse".
        # data[3]: PSI is optional, only for 2D required
        # TODO: is psi mandatory in 2D? Should ierror be mandatory?
        #B:Either PSI and Q or QX and QY are required. Useful to calculate the 
        #B:missing matrices and allow use of both QX and QY or Q and PSI.
        # can psi be present without ierror?
        #B:yes. but without an error estimate on the intensity, results are
        #B:ambiguous

        # make single array: one row per intensity and its associated values
        # selection of intensity is shorter this way: dataset[validIndices]
        # enforce a certain shape here (removed ReshapeFitdata)
        data = numpy.vstack([d for d in data if d is not None]).T
        if isOriginal:
            self.dataset = SASData("SAS data provided", data)
        else:
            self.dataset = SASData("SAS data provided", None)
            self.dataset.prepared = data
        McSASParameters.contribParamBounds = list(self.dataset.sphericalSizeEst())

    def setParameter(self, kwargs):
        """Sets the supplied Parameters given in keyword-value pairs for known
        setting keywords (unknown key-value pairs are skipped).
        If a supplied parameter is one of the function names, it is stored in
        the self.Functions dict.
        """
        for key in kwargs.keys():
            found = False
            param = getattr(self, key, None)
            if isinstance(param, FitParameterBase):
                param.setValue(kwargs[key])
                found = True
            for cls in McSASParameters, ScatteringModel:
                if key in cls.propNames():
                    value = kwargs[key]
                    setattr(cls, key, value)
                    found = True
                    break
            if found:
                del kwargs[key]
            else:
                logging.warning("Unknown McSAS parameter specified: '{0}'"
                                .format(key))

    ######################################################################
    ##################### Pre-optimisation Functions #####################
    ######################################################################

    def checkParameters(self):
        """Checks for the Parameters, for example to make sure
        histbins is defined for all, or to check if all Parameters fall
        within their limits.
        For now, all I need is a check that McSASParameters.histogramBins is a 1D vector
        with n values, where n is the number of Parameters specifying
        a shape.
        """
        def fixLength(valueList):
            if not isList(valueList):
                valueList = [valueList for dummy in range(self.model.paramCount())]
            elif len(valueList) > self.model.paramCount():
                del valueList[self.model.paramCount():]
            elif len(valueList) < self.model.paramCount():
                nMissing = self.model.paramCount() - len(valueList)
                valueList.extend([valueList[0] for dummy in range(nMissing)])
            return valueList

        McSASParameters.histogramBins = fixLength(self.histogramBins.value())
        McSASParameters.histogramXScale = fixLength(
                                            McSASParameters.histogramXScale)
        self.model.updateParamBounds(McSASParameters.contribParamBounds)

    def optimScalingAndBackground(self, intObs, intCalc, intError, sc, ver = 2,
            outputIntensity = False):
        """
        Optimizes the scaling and background factor to match *intCalc* closest
        to intObs. 
        Returns an array with scaling factors. Input initial guess *sc* has 
        to be a two-element array with the scaling and background.

        **Input arguments:**

        :arg intObs: An array of *measured*, respectively *observed*
                     intensities
        :arg intCalc: An array of intensities which should be scaled to match
                      *intObs*
        :arg intError: An array of uncertainties to match *intObs*
        :arg sc: A 2-element array of initial guesses for scaling
                 factor and background
        :arg ver: *(optional)* Can be set to 1 for old version, more robust
                  but slow, default 2 for new version,
                  10x faster than version 1
        :arg outputIntensity: *(optional)* Return the scaled intensity as
                              third output argument, default: False
        :arg background: *(optional)* Enables a flat background contribution,
                         default: True

        :returns: (*sc*, *conval*): A tuple of an array containing the
                  intensity scaling factor and background and the reduced
                  chi-squared value.
        """
        def csqr(sc, intObs, intCalc, intError):
            """Least-squares intError for use with scipy.optimize.leastsq"""
            return (intObs - sc[0]*intCalc - sc[1]) / intError
        
        def csqr_nobg(sc, intObs, intCalc, intError):
            """Least-squares intError for use with scipy.optimize.leastsq,
            without background """
            return (intObs - sc[0]*intCalc) / intError

        def csqr_v1(intObs, intCalc, intError):
            """Least-squares for data with known intError,
            size of parameter-space not taken into account."""
            return sum(((intObs - intCalc)/intError)**2) / size(intObs)

        intObs = intObs.flatten()
        intCalc = intCalc.flatten()
        intError = intError.flatten()
        # we need an McSAS instance anyway to call this method
        background = self.findBackground.value()
        if ver == 2:
            """uses scipy.optimize.leastsqr"""
            if background:
                sc, dummySuccess = optimize.leastsq(
                        csqr, sc, args = (intObs, intCalc, intError),
                        full_output = False)
                conval = csqr_v1(intObs, sc[0]*intCalc + sc[1], intError)
            else:
                sc, dummySuccess = optimize.leastsq(
                        csqr_nobg, sc, args = (intObs, intCalc, intError),
                        full_output = False)
                sc[1] = 0.0
                conval = csqr_v1(intObs, sc[0]*intCalc, intError)
        else:
            """using scipy.optimize.fmin"""
            # Background can be set to False to just find the scaling factor.
            if background:
                sc = optimize.fmin(
                    lambda sc: csqr_v1(intObs, sc[0]*intCalc + sc[1], intError),
                    sc, full_output = False, disp = 0)
                conval = csqr_v1(intObs, sc[0]*intCalc + sc[1], intError)
            else:
                sc = optimize.fmin(
                    lambda sc: csqr_v1(intObs, sc[0]*intCalc, intError),
                    sc, full_output = False, disp = 0)
                sc[1] = 0.0
                conval = csqr_v1(intObs, sc[0]*intCalc, intError)

        if outputIntensity:
            return sc, conval, sc[0]*intCalc + sc[1]
        else:
            return sc, conval

    def _passthrough(self,In):
        """A passthrough mechanism returning the input unchanged"""
        return In


    ######################################################################
    ####################### optimisation Functions #######################
    ######################################################################

    def analyse(self):
        """This function runs the Monte Carlo optimisation a multitude
        (*numReps*) of times. If convergence is not achieved, it will try 
        again for a maximum of *maxRetries* attempts.
        """
        data = self.dataset.prepared
        # get settings
        priors = McSASParameters.priors
        prior = McSASParameters.prior
        maxRetries = McSASParameters.maxRetries
        numContribs = self.numContribs.value()
        numReps = self.numReps.value()
        minConvergence = self.convergenceCriterion.value()
        if not any([p.isActive() for p in self.model.params()]):
            numContribs, numReps = 1, 1
        # find out how many values a shape is defined by:
        contributions = zeros((numContribs, self.model.paramCount(), numReps))
        numIter = zeros(numReps)
        contribIntensity = zeros([1, len(data), numReps])
        start = time.time() # for time estimation and reporting

        # This is the loop that repeats the MC optimization numReps times,
        # after which we can calculate an uncertainty on the Results.
        priorsflag = False
        for nr in range(numReps):
            if (len(prior) <= 0 and len(priors) > 0) or priorsflag:
                # this flag needs to be set as prior will be set after
                # the first pass
                priorsflag = True
                McSASParameters.prior = priors[:, :, nr%size(priors, 2)]
            # keep track of how many failed attempts there have been
            nt = 0
            # do that MC thing! 
            convergence = inf
            while convergence > minConvergence:
                # retry in the case we were unlucky in reaching
                # convergence within MaximumIterations.
                nt += 1
                (contributions[:, :, nr], contribIntensity[:, :, nr],
                 convergence, details) = self.mcFit(
                                numContribs, minConvergence,
                                outputIntensity = True, outputDetails = True)
                if len(contributions) <= 1:
                    break # nothing to fit
                if self.stop:
                    logging.warning("Stop button pressed, exiting...")
                    return
                if nt > maxRetries:
                    # this is not a coincidence.
                    # We have now tried maxRetries+2 times
                    logging.warning("Could not reach optimization criterion "
                                    "within {0} attempts, exiting..."
                                    .format(maxRetries+2))
                    return
            # keep track of how many iterations were needed to reach converg.
            numIter[nr] = details.get('numIterations', 0)

            # in minutes:
            tottime = (time.time() - start)/60. # total elapsed time
            avetime = (tottime / (nr+1)) # average time per MC optimization
            remtime = (avetime*numReps - tottime) # est. remaining time
            logging.info("finished optimization number {0} of {1}\n"
                    "  total elapsed time: {2} minutes\n"
                    "  average time per optimization {3} minutes\n"
                    "  total time remaining {4} minutes"
                    .format(nr+1, numReps, tottime, avetime, remtime))
        
        # store in output dict
        self.result.append(dict(
            contribs = contributions, # Rrep
            fitIntensityMean = contribIntensity.mean(axis = 2),
            fitIntensityStd = contribIntensity.std(axis = 2),
            fitQ = data[:, 0],
            # average number of iterations for all repetitions
            numIter = numIter.mean()))

    def mcFit(self, numContribs, minConvergence,
              outputIntensity = False, outputDetails = False,
              outputIterations = False):
        """
        Object-oriented, shape-flexible core of the Monte Carlo procedure.
        Takes optional arguments:

        *outputIntensity*:
            Returns the fitted intensity besides the Result

        *outputDetails*:
            details of the fitting procedure, number of iterations and so on

        *outputIterations*:
            Returns the Result on every successful iteration step, useful for
            visualising the entire Monte Carlo optimisation procedure for
            presentations.
        """
        data = self.dataset.prepared
        prior = McSASParameters.prior
        rset = numpy.zeros((numContribs, self.model.activeParamCount()))
        details = dict()
        # index of sphere to change. We'll sequentially change spheres,
        # which is perfectly random since they are in random order.
        
        q = data[:, 0]
        # generate initial set of spheres
        if size(prior) == 0:
            if McSASParameters.startFromMinimum:
                for idx, param in enumerate(self.model.params()):
                    mb = min(param.valueRange())
                    if mb == 0: # FIXME: compare with EPS eventually?
                        mb = pi / q.max()
                    rset[:, idx] = numpy.ones(numContribs) * mb * .5
            else:
                rset = self.model.generateParameters(numContribs)
        elif prior.shape[0] != 0: #? and size(numContribs) == 0:
                                  # (didnt understand this part)
            numContribs = prior.shape[0]
            rset = prior
        elif prior.shape[0] == numContribs:
            rset = prior
        elif prior.shape[0] < numContribs:
            logging.info("size of prior is smaller than numContribs. "\
                    "duplicating random prior values")
            randomIndices = numpy.random.randint(prior.shape[0],
                            size = numContribs - prior.shape[0])
            rset = numpy.concatenate((prior, prior[randomIndices, :]))
            logging.info("size now: {}".format(rset.shape))
        elif prior.shape[0] > numContribs:
            logging.info("Size of prior is larger than numContribs. "\
                    "removing random prior values")
            # remaining choices
            randomIndices = numpy.random.randint(prior.shape[0],
                                                 size = numContribs)
            rset = prior[randomIndices, :]
            logging.info("size now: {}".format(rset.shape))

        # call the model for each parameter value explicitly
        # otherwise the model gets complex for multiple params incl. fitting
        it, vset = self.calcModel(data, rset)
        vst = sum(vset**2) # total volume squared

        # Optimize the intensities and calculate convergence criterium
        # SMEAR function goes here
        it = self.model.smear(it)
        intensity = data[:, 1]
        intError = data[:, 2]
        sci = intensity.max() / it.max() # init. guess for the scaling factor
        bgi = intensity.min()
        sc, conval = self.optimScalingAndBackground(
                intensity, it/vst, intError, numpy.array([sci, bgi]), ver = 1)
        # reoptimize with V2, there might be a slight discrepancy in the
        # residual definitions of V1 and V2 which would prevent optimization.
        sc, conval = self.optimScalingAndBackground(
                intensity, it/vst, intError, sc)
        logging.info("Initial Chi-squared value: {0}".format(conval))

        if outputIterations:
            logging.warning('outputIterations functionality inoperable')
            #will not work, because of the different size of rset with multi-
            #parameter models.
            ## Output each iteration, starting with number 0. Iterations will
            ## be stored in details['paramDistrib'], details['intensityFitted'],
            ## details['convergenceValue'], details['scalingFactor'] and
            ## details['priorUnaccepted'] listing the unaccepted number of
            ## moves before the recorded accepted move.

            ## new iterations will (have to) be appended to this, cannot be
            ## zero-padded due to size constraints
            #details['paramDistrib'] = rset[:, newaxis]
            #details['intensityFitted'] = (it/vst*sc[0] + sc[1])[:, newaxis]
            #details['convergenceValue'] = conval[newaxis]
            #details['scalingFactor'] = sc[:, newaxis]
            #details['priorUnaccepted'] = numpy.array(0)[newaxis]

        # start the MC procedure
        intObs = data[:, 1]
        intError = data[:, 2]
        start = time.time()
        numMoves = 0 # tracking the number of moves
        numNotAccepted = 0
        numIter = 0
        ri = 0
        lastUpdate = 0
        while (len(vset) > 1 and # see if there is a distribution at all
               conval > minConvergence and
               numIter < self.maxIterations.value() and
               not self.stop):
            rt = self.model.generateParameters()
            ft = self.model.ff(data, rt)
            vtt = self.model.vol(rt)
            itt = (ft**2 * vtt**2).flatten()
            # Calculate new total intensity
            itest = None
            # speed up by storing all intensities above, needs lots of memory
            # itest = (it - iset[:, ri] + itt)
            fo = self.model.ff(data, rset[ri].reshape((1, -1)))
            io = (fo**2 * vset[ri]**2).flatten()
            itest = (it.flatten() - io + itt)

            # SMEAR function goes here
            itest = self.model.smear(itest)
            vstest = (sqrt(vst) - vset[ri])**2 + vtt**2
            # optimize intensity and calculate convergence criterium
            # using version two here for a >10 times speed improvement
            sct, convalt = self.optimScalingAndBackground(
                                    intObs, itest/vstest, intError, sc)
            # test if the radius change is an improvement:
            if convalt < conval: # it's better
                # replace current settings with better ones
                rset[ri], sc, conval = rt, sct, convalt
                it, vset[ri], vst = itest, vtt, vstest
                logging.info("Improvement in iteration number {0}, "
                             "Chi-squared value {1:f} of {2:f}\r"
                             .format(numIter, conval, minConvergence))
                numMoves += 1
                if outputIterations:
                    # output each iteration, starting with number 0. 
                    # Iterations will be stored in details['paramDistrib'],
                    # details['intensityFitted'], details['convergenceValue'],
                    # details['scalingFactor'] and details['priorUnaccepted']
                    # listing the unaccepted number of moves before the
                    # recorded accepted move.

                    # new iterations will (have to) be appended to this,
                    # cannot be zero-padded due to size constraints
                    details['paramDistrib'] = numpy.dstack(
                            (details['paramDistrib'], rset[:, :, newaxis]))
                    details['intensityFitted'] = numpy.hstack(
                            (details['intensityFitted'],
                             (itest/vstest*sct[0] + sct[1]).T))
                    details['convergenceValue'] = numpy.concatenate(
                            (details['convergenceValue'], convalt[newaxis]))
                    details['scalingFactor'] = numpy.hstack(
                            (details['scalingFactor'], sct[:, newaxis]))
                    details['priorUnaccepted'] = numpy.concatenate(
                            (details['priorUnaccepted'],
                             numpy.array((numNotAccepted, ))))
                numNotAccepted = 0
            else:
                # number of non-accepted moves,
                # resets to zero after on accepted move
                numNotAccepted += 1
            if time.time() - lastUpdate > 0.25:
                # update twice a sec max -> speedup for fast models
                # because output takes much time especially in GUI
                # process events, check for user input
                # TODO: don't need this, if we calc in separate processes (multiprocessing)
                # the gui would have an own thread and will not be blocked by calc
                processEventLoop()
                lastUpdate = time.time()
            # move to next sphere in list, loop if last sphere
            ri = (ri + 1) % (numContribs)
            numIter += 1 # add one to the iteration number

        #print # for progress print in the loop
        if numIter >= self.maxIterations.value():
            logging.warning("Exited due to max. number of iterations ({0}) "
                            "reached".format(numIter))
        else:
            logging.info("normal exit")
        # the +0.001 seems necessary to prevent a divide by zero error
        # on some Windows systems.
        elapsed = time.time() - start + 1e-3
        logging.info("Number of iterations per second: {0}".format(
                        numIter/elapsed))
        logging.info("Number of valid moves: {0}".format(numMoves))
        logging.info("Final Chi-squared value: {0}".format(conval))
        details['numIterations'] = numIter
        details['numMoves'] = numMoves
        details['elapsed'] = elapsed

        ifinal = it / sum(vset**2)
        ifinal = self.model.smear(ifinal)
        sc, conval = self.optimScalingAndBackground(
                            intObs, ifinal, intError, sc)

        result = [rset]
        if outputIntensity:
            result.append((ifinal * sc[0] + sc[1]))
        result.append(conval)
        if outputDetails:
            result.append(details)
        # returning <rset, intensity, conval, details>
        return result

    #####################################################################
    #################### Post-optimisation Functions ####################
    #####################################################################

    def histogram(self, contribs = None):
        """
        Takes the *contribs* result from the :py:meth:`McSAS.analyse` function
        and calculates the corresponding volume- and number fractions for each
        contribution as well as the minimum observability limits. It will
        subsequently bin the Result across the range for histogramming 
        purposes.

        While the volume-weighted distribution will be in absolute units
        (providing volume fractions of material within a given size range),
        the number distributions have been normalized to 1.
        
        Output a list of dictionaries with one dictionary per shape parameter:

            *histogramXLowerEdge*: array
                histogram bin left edge position (x-axis in histogram)
            *histogramXMean*: array
                Center positions for the size histogram bins
                (x-axis in histogram, used for errorbars)
            *histogramXWidth*: array
                histogram bin width (x-axis in histogram,
                defines bar plot bar widths)
            *volumeHistogramYMean*: array
                Volume-weighted particle size distribution values for
                all *numReps* Results (y-axis bar height)
            *numberHistogramYMean*: array
                Number-weighted analogue of the above *volumeHistogramYMean*
            *volumeHistogramRepetitionsY*: size (histogramBins x numReps) 
                array Volume-weighted particle size distribution bin values for 
                each MC fit repetition (whose mean is *volumeHistogramYMean*, 
                and whose sample standard deviation is *volumeHistogramYStd*)
            *numberHistogramRepetitionsY*: size (histogramBins x numReps) 
                array Number-weighted particle size distribution bin values
                for each MC fit repetition
            *volumeHistogramYStd*: array
                Standard deviations of the corresponding volume-weighted size
                distribution bins, calculated from *numReps* repetitions of
                the model fitting function
            *numberHistogramYStd*: array
                Standard deviation for the number-weigthed distribution
            *volumeFraction*: size (numContribs x numReps) array
                Volume fractions for each of numContribs contributions 
                in each of numReps iterations
            *numberFraction*: size (numContribs x numReps) array
                Number fraction for each contribution
            *totalVolumeFraction*: size (numReps) array
                Total scatterer volume fraction for each of the *numReps*
                iterations
            *totalNumberFraction*: size (numReps) array
                Total number fraction 
            *minimumRequiredVolume*: size (numContribs x numReps) array
                minimum required volume fraction for each contribution to
                become statistically significant.
            *minimumRequiredNumber*: size (numContribs x numReps) array
                number-weighted analogue to *minimumRequiredVolume*
            *volumeHistogramMinimumRequired*: size (histogramXMean) array 
                array with the minimum required volume fraction per bin to
                become statistically significant. Used to display minimum
                required level in histogram.
            *numberHistogramMinimumRequired*: size (histogramXMean) array
                number-weighted analogue to *volumeHistogramMinimumRequired*
            *scalingFactors*: size (2 x numReps) array
                Scaling and background values for each repetition. Used to
                display background level in data and fit plot.
        """
        if not isList(self.result) or not len(self.result):
            logging.info("There are no results to histogram, breaking up.")
            return
        if contribs is None:
            contribs = self.result[0]['contribs']
        numContribs, dummy, numReps = contribs.shape

        # volume fraction for each contribution
        volumeFraction = zeros((numContribs, numReps))
        # number fraction for each contribution
        numberFraction = zeros((numContribs, numReps))
        # volume fraction for each contribution
        qm = zeros((numContribs, numReps))
        # volume frac. for each histogram bin
        minReqVol = zeros((numContribs, numReps)) 
        # number frac. for each histogram bin
        minReqNum = zeros((numContribs, numReps))
        totalVolumeFraction = zeros((numReps))
        totalNumberFraction = zeros((numReps))
        # Intensity scaling factors for matching to the experimental
        # scattering pattern (Amplitude A and flat background term b,
        # defined in the paper)
        scalingFactors = zeros((2, numReps))

        # data, store it in result too, enables to postprocess later
        # store the model instance too
        data = self.dataset.prepared
        q = data[:, 0]
        intensity = data[:, 1]
        intError = data[:, 2]

        # loop over each repetition
        for ri in range(numReps):
            rset = contribs[:, :, ri] # single set of R for this calculation
            # compensated volume for each sphere in the set
            it, vset = self.calcModel(data, rset)
            vst = sum(vset**2) # total compensated volume squared 
            it = self.model.smear(it)
            
            # Now for each sphere, calculate its volume fraction
            # (p_c compensated):
            # compensated volume for each sphere in
            # the set Vsa = 4./3*pi*Rset**(3*PowerCompensationFactor)
            # Vsa = VOLfunc(Rset, PowerCompensationFactor)
            vsa = vset # vset did not change here
            # And the real particle volume:
            # compensated volume for each sphere in
            # the set Vsa = 4./3*pi*Rset**(3*PowerCompensationFactor)
            # Vpa = VOLfunc(Rset, PowerCompensationFactor = 1.)
            vpa = zeros(rset.shape[0])
            for i in numpy.arange(rset.shape[0]):
                vpa[i] = self.model.vol(rset[i].reshape((1, -1)), compensationExponent = 1.0)
            ## TODO: same code than in mcfit pre-loop around line 1225 ff.
            # initial guess for the scaling factor.
            sci = intensity.max() / it.max()
            bgi = intensity.min()
            # optimize scaling and background for this repetition
            sc, conval = self.optimScalingAndBackground(
                    intensity, it, intError, (sci, bgi))
            scalingFactors[:, ri] = sc # scaling and bgnd for this repetition.
            # a set of volume fractions
            volumeFraction[:, ri] = (
                    sc[0] * vsa**2/(vpa * McSASParameters.deltaRhoSquared)
                    ).flatten()
            totalVolumeFraction[ri] = sum(volumeFraction[:, ri])
            numberFraction[:, ri] = volumeFraction[:, ri]/vpa.flatten()
            totalNumberFraction[ri] = sum(numberFraction[:, ri])

            for c in range(numContribs): # for each sphere
                # calculate the observability (the maximum contribution for
                # that sphere to the total scattering pattern)
                # NOTE: no need to compensate for p_c here, we work with
                # volume fraction later which is compensated by default.
                # additionally, we actually do not use this value.
                ffset = self.model.ff(data, rset[c].reshape((1, -1)))
                ir = (ffset**2 * vset[c]**2).flatten()
                # determine where this maximum observability is
                # of contribution c (index)
                qmi = numpy.argmax(ir.flatten()/it.flatten())
                # point where the contribution of c is maximum
                qm[c, ri] = q[qmi]
                minReqVol[c, ri] = (
                        intError * volumeFraction[c, ri]
                                / (sc[0] * ir)).min()
                minReqNum[c, ri] = minReqVol[c, ri] / vpa[c]

            numberFraction[:, ri] /= totalNumberFraction[ri]
            minReqNum[:, ri] /= totalNumberFraction[ri]

        # now we histogram over each variable
        # for each variable parameter we define,
        # we need to histogram separately.
        for paramIndex, param in enumerate(self.model.activeParams()):

            # Now bin whilst keeping track of which contribution ends up in
            # which bin: set bin edge locations
            if McSASParameters.histogramXScale[paramIndex] == 'linear':
                # histogramXLowerEdge contains #histogramBins+1 bin edges,
                # or class limits.
                histogramXLowerEdge = numpy.linspace(
                        min(param.valueRange()),
                        max(param.valueRange()),
                        McSASParameters.histogramBins[paramIndex] + 1)
            else:
                histogramXLowerEdge = 10**numpy.linspace(
                        log10(min(param.valueRange())),
                        log10(max(param.valueRange())),
                        McSASParameters.histogramBins[paramIndex] + 1)

            def initHist(reps = 0):
                """Helper for histogram array initialization"""
                shp = McSASParameters.histogramBins[paramIndex]
                if reps > 0:
                    shp = (McSASParameters.histogramBins[paramIndex], reps)
                return numpy.zeros(shp)

            # total volume fraction contribution in a bin
            volHistRepY = initHist(numReps)
            # total number fraction contribution in a bin
            numHistRepY = initHist(numReps)
            # minimum required number of contributions /in a bin/ to make
            # a measurable impact
            minReqVolBin = initHist(numReps)
            minReqNumBin = initHist(numReps)
            histogramXMean = initHist()
            volHistMinReq = initHist()
            numHistMinReq = initHist()

            logging.debug('shape contribs: {}, paramIndex: {}'.format(shape(contribs),paramIndex))
            for ri in range(numReps):
                # single set of R for this calculation
                rset = contribs[:, paramIndex, ri]
                for bini in range(McSASParameters.histogramBins[paramIndex]):
                    # indexing which contributions fall into the radius bin
                    binMask = (  (rset >= histogramXLowerEdge[bini])
                               * (rset <  histogramXLowerEdge[bini + 1]))
                    # y contains the volume fraction for that radius bin
                    volHistRepY[bini, ri] = sum(volumeFraction[binMask, ri])
                    numHistRepY[bini, ri] = sum(numberFraction[binMask, ri])
                    if not any(binMask):
                        minReqVolBin[bini, ri] = 0
                        minReqNumBin[bini, ri] = 0
                    else:
                        # why? ignored anyway
                        # minReqVolBin[bini, ri] = minReqVol[binMask, ri].max()
                        minReqVolBin[bini, ri] = minReqVol[binMask, ri].mean()
                        # ignored anyway
                        # minReqNumBin[bini, ri] = minReqNum[binMask, ri].max()
                        minReqNumBin[bini, ri] = minReqNum[binMask, ri].mean()
                    if isnan(volHistRepY[bini, ri]):
                        volHistRepY[bini, ri] = 0.
                        numHistRepY[bini, ri] = 0.
            for bini in range(McSASParameters.histogramBins[paramIndex]):
                histogramXMean[bini] = histogramXLowerEdge[bini:bini+2].mean()
                vb = minReqVolBin[bini, :]
                volHistMinReq[bini] = vb[vb < inf].max()
                nb = minReqNumBin[bini, :]
                numHistMinReq[bini] = nb[nb < inf].max()
            volHistYMean = volHistRepY.mean(axis = 1)
            numHistYMean = numHistRepY.mean(axis = 1)
            volHistYStd = volHistRepY.std(axis = 1)
            numHistYStd = numHistRepY.std(axis = 1)

            # store the results, we'll fix this later by a proper structure
            while paramIndex >= len(self.result):
                self.result.append(dict())
            self.result[paramIndex].update(dict(
                histogramXLowerEdge = histogramXLowerEdge,
                histogramXMean = histogramXMean,
                histogramXWidth = diff(histogramXLowerEdge),
                volumeHistogramRepetitionsY = volHistRepY,
                numberHistogramRepetitionsY = numHistRepY,
                volumeHistogramYMean = volHistYMean,
                volumeHistogramYStd = volHistYStd,
                numberHistogramYMean = numHistYMean,
                numberHistogramYStd = numHistYStd,
                volumeHistogramMinimumRequired = volHistMinReq,
                minimumRequiredVolume = minReqVol,
                volumeFraction = volumeFraction,
                totalVolumeFraction = totalVolumeFraction,
                numberHistogramMinimumRequired = numHistMinReq,
                minimumRequiredNumber = minReqNum,
                numberFraction = numberFraction,
                totalNumberFraction = totalNumberFraction,
                scalingFactors = scalingFactors))

    def gen2DIntensity(self):
        """
        This function is optionally run after the histogram procedure for
        anisotropic images, and will calculate the MC fit intensity in
        image form
        """
        contribs = self.result[0]['contribs']
        numContribs, dummy, numReps = contribs.shape

        # load original Dataset
        data = self.dataset.origin
        q = data[:, 0]
        # we need to recalculate the result in two dimensions
        kansas = shape(q) # we will return to this shape
        q = q.flatten()

        logging.info("Recalculating final 2D intensity, this may take some time")
        # for each Result
        intAvg = zeros(shape(q))
        # TODO: for which parameter?
        scalingFactors = self.result[0]['scalingFactors']
        for ri in range(numReps):
            logging.info('regenerating set {} of {}'.format(ri, numReps-1))
            rset = contribs[:, :, ri]
            # calculate their form factors
            it, vset = self.calcModel(data, rset)
            vst = sum(vset**2) # total volume squared
            # Optimize the intensities and calculate convergence criterium
            it = self.model.smear(it)
            intAvg = intAvg + it*scalingFactors[0, ri] + scalingFactors[1, ri]
        # print "Initial conval V1", Conval1
        intAvg /= numReps
        # mask (lifted from clipDataset)
        validIndices = SASData.clipMask(data,
                                        McSASParameters.qBounds,
                                        McSASParameters.psiBounds,
                                        McSASParameters.maskNegativeInt,
                                        McSASParameters.maskZeroInt)
        intAvg = intAvg[validIndices]
        # shape back to imageform
        self.result[0]['intensity2d'] = reshape(intAvg, kansas)

    def exportCSV(self, filename, *args, **kwargs):
        """
        This function writes a semicolon-separated csv file to [filename]
        containing an arbitrary number of output variables *\*args*.
        In case of variable length columns, empty fields will contain ''.

        Optional last argument is a keyword-value argument:
        :py:arg:paramIndex = [integer], indicating which shape parameter it
        is intended to draw upon. VariableNumber can also be a list or array
        of integers, of the same length as the number of output variables
        *\*args* in which case each output variable is matched with a shape
        parameter index. Default is zero.

        Input arguments should be names of fields in *self.result*.
        For example::

            McSAS.exportCSV('hist.csv', 'histogramXLowerEdge',
                            'histogramXWidth', 'volumeHistogramYMean',
                            'volumeHistogramYStd', paramIndex = 0)

        I.e. just stick on as many columns as you'd like. They will be
        flattened by default. A header with the result keyword names will be
        added.
        
        Existing files with the same filename will be overwritten by default.
        """
        vna = numpy.zeros(len(args), dtype = int)
        vni = kwargs.pop('paramIndex', None)
        if vni is not None:
            if isList(vni):
                if len(vni) != len(args):
                    print("Error in exportCSV, supplied list of "
                          "variablenumbers does not have the length of 1 or"
                          "the same length as the list of output variables.")
                    return
                for vi in range(len(args)):
                    vna[vi] = vni[vi]
            else:
                # single integer value
                vna += vni
                
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
            inlist.append(self.result[vna[argi]][args[argi]].flatten())
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

    def plot(self, axisMargin = 0.3, parameterIdx = None):
        # runs matplotlib in a separate process
        # keeps plot window open on windows
        # does not block if another calculation is started
        pickleParams = [p.attributes() for p in self.model.params()]
        plotArgs = (self.result, self.dataset, pickleParams,
                    axisMargin, parameterIdx, self.figureTitle)
        # on Windows the plot figure blocks the app until it is closed
        # -> we have to call matplotlib plot in another thread (1.3.1)
        # on linux it does not block, can show multiple figures (1.0.1)
        if sys.platform.lower().startswith("win") and not isFrozen():
            # does not work in linux: UI has to run in main thread (X server error)
            # -> move (headless) calculations to another
            from multiprocessing import Process
            proc = Process(target = plotResults, args = plotArgs)
            proc.start()
        else:
            plotResults(*plotArgs)

    def rangeInfo(self, valueRange = [0, inf], paramIndex = 0, weighting=None):
        """Calculates the total volume or number fraction of the MC result
        within a given range, and returns the total numer or volume fraction
        and its standard deviation over all nreps as well as the first four
        distribution moments: mean, variance, skewness and kurtosis
        (Pearson's definition).
        Will use the *histogramWeighting* parameter or the optional 
        rangeInfo parameter *weighting* for determining whether to 
        return the volume or number-weighted values.

        Input arguments are:

            *valueRange*
              The radius range in which the moments are to be calculated
            *paramIndex*
              Which shape parameter the moments are to be calculated for
              (e.g. 0 = width, 1 = length, 2 = orientation)
            *weighting*
              Can be set to "volume" or "number", otherwise it is set to
              the *histogramWeighting* parameter of the McSAS main function

        Returns a 4-by-2 array, with the values and their sample standard
        deviations over all *numRepetitions*.
        """
        contribs = self.result[0]['contribs']
        numContribs, dummy, numReps = contribs.shape

        volumeFraction = self.result[paramIndex]['volumeFraction']
        numberFraction = self.result[paramIndex]['numberFraction']
        totalVolumeFraction = self.result[paramIndex]['totalVolumeFraction']
        totalNumberFraction = self.result[paramIndex]['totalNumberFraction']
        # Intensity scaling factors for matching to the experimental
        # scattering pattern (Amplitude A and flat background term b,
        # defined in the paper)
        scalingFactors = self.result[paramIndex]['scalingFactors']

        val = numpy.zeros(numReps) # total value
        mu  = numpy.zeros(numReps) # moments..
        var = numpy.zeros(numReps) # moments..
        skw = numpy.zeros(numReps) # moments..
        krt = numpy.zeros(numReps) # moments..

        if weighting is None:
            weighting=McSASParameters.histogramWeighting
        # loop over each repetition
        for ri in range(numReps):
            # the single set of R for this calculation
            rset = contribs[:, paramIndex, ri]
            validRange = (  (rset > min(valueRange))
                          * (rset < max(valueRange)))
            rset = rset[validRange]
            # compensated volume for each sphere in the set
            vset = volumeFraction[validRange, ri]
            nset = numberFraction[validRange, ri]

            if weighting == 'volume':
                val[ri] = sum(vset)
                mu[ri]  = sum(rset * vset)/sum(vset)
                var[ri] = sum( (rset - mu[ri])**2 * vset )/sum(vset)
                sigma   = numpy.sqrt(abs(var[ri]))
                skw[ri] = (  sum( (rset-mu[ri])**3 * vset )
                           / (sum(vset) * sigma**3))
                krt[ri] = ( sum( (rset-mu[ri])**4 * vset )
                           / (sum(vset) * sigma**3))
            elif weighting == 'number':
                val[ri] = sum(nset)
                mu[ri]  = sum(rset * nset)/sum(nset)
                var[ri] = sum( (rset-mu[ri])**2 * nset )/sum(nset)
                sigma   = numpy.sqrt(abs(var[ri]))
                skw[ri] = ( sum( (rset-mu[ri])**3 * nset )
                           / (sum(nset) * sigma**3))
                krt[ri] = ( sum( (rset-mu[ri])**4 * nset )
                           / (sum(nset) * sigma**4))
            else:
                logging.error("Moment calculation: "
                              "unrecognised histogramWeighting value!")
                return None

        # now we can calculate the intensity contribution by the subset of
        # spheres highlighted by the range:
        logging.info("Calculating partial intensity contribution of range")
        # loop over each repetition
        partialIntensities = numpy.zeros(
                (numReps, self.result[0]['fitQ'].shape[0]))

        data = self.dataset.prepared
        for ri in range(numReps):
            rset = contribs[:, paramIndex, ri]
            validRange = (  (rset > min(valueRange))
                          * (rset < max(valueRange)))
            # BP: this one did not work for multi-parameter models
            # rset = rset[validRange][:, newaxis]
            rset = contribs[validRange,:,ri]
            # compensated volume for each sphere in the set
            it, vset = self.calcModel(data, rset)
            it = self.model.smear(it)
            sc = scalingFactors[:, ri] # scaling and background for this repetition.
            # a set of volume fractions
            partialIntensities[ri, :] = it.flatten() * sc[0]

        rangeInfoResult = dict(
                partialIntensityMean = partialIntensities.mean(axis = 0),
                partialIntensityStd  = partialIntensities.std(axis = 0),
                partialQ             = self.result[0]['fitQ'].flatten(),
                totalValue           = [val.mean(), val.std(ddof = 1)],
                mean                 = [ mu.mean(),  mu.std(ddof = 1)],
                variance             = [var.mean(), var.std(ddof = 1)],
                skew                 = [skw.mean(), skw.std(ddof = 1)],
                kurtosis             = [krt.mean(), krt.std(ddof = 1)]
        )
        self.result[paramIndex].update(rangeInfoResult)
        return rangeInfoResult

    # move this to ScatteringModel eventually?
    # which additional output might by useful/required?
    # btw: called 4 times
    def calcModel(self, data, rset):
        """Calculates the total intensity and scatterer volume contributions
        using the current model."""
        it = 0
        vset = zeros(rset.shape[0])
        for i in numpy.arange(rset.shape[0]):
            vset[i] = self.model.vol(rset[i].reshape((1, -1)))
            # calculate their form factors
            ffset = self.model.ff(data, rset[i].reshape((1, -1)))
            # a set of intensities
            it += ffset**2 * vset[i]**2
        return it.flatten(), vset

# vim: set ts=4 sts=4 sw=4 tw=0:
