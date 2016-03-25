"""
Python implementation of the fast ICA algorithms.

Reference: Tables 8.3 and 8.4 page 196 in the book:
Independent Component Analysis, by  Hyvarinen et al.
"""

# Author: Pierre Lafaye de Micheaux, Stefan van der Walt, Gael Varoquaux
# License: BSD 3 clause

import numpy as np
from scipy import linalg
import types

__all__ = ['fastica']


def _gs_decorrelation(w, W, j):
    """ Gram-Schmidt-like decorrelation. """
    t = np.zeros_like(w)
    for u in range(j):
        t = t + np.dot(w, W[u]) * W[u]
        w -= t
    return w


def _ica_def(X, tol, g, gprime, fun_args, maxit, w_init):
    """Deflationary FastICA using fun approx to neg-entropy function

    Used internally by FastICA.
    """

    n_comp = w_init.shape[0]
    W = np.zeros((n_comp, n_comp), dtype=float)

    # j is the index of the extracted component
    for j in range(n_comp):
        w = w_init[j, :].copy()
        w /= np.sqrt((w**2).sum())

        n_iterations = 0
        # we set lim to tol+1 to be sure to enter at least once in next while
        lim = tol + 1 
        while ((lim > tol) & (n_iterations < (maxit-1))):
            wtx = np.dot(w.T, X)
            gwtx = g(wtx, fun_args)
            g_wtx = gprime(wtx, fun_args)
            w1 = (X * gwtx).mean(axis=1) - g_wtx.mean() * w
            
            _gs_decorrelation(w1, W, j)
            
            w1 /= np.sqrt((w1**2).sum())

            lim = np.abs(np.abs((w1 * w).sum()) - 1)
            w = w1
            n_iterations = n_iterations + 1
            
        W[j, :] = w

    return W


def _sym_decorrelation(W):
    """ Symmetric decorrelation """
    K = np.dot(W, W.T)
    s, u = linalg.eigh(K) 
    # u (resp. s) contains the eigenvectors (resp. square roots of 
    # the eigenvalues) of W * W.T 
    u, W = [np.asmatrix(e) for e in (u, W)]
    W = (u * np.diag(1.0/np.sqrt(s)) * u.T) * W  # W = (W * W.T) ^{-1/2} * W
    return np.asarray(W)


def _ica_par(X, tol, g, gprime, fun_args, maxit, w_init):
    """Parallel FastICA.

    Used internally by FastICA.

    """
    n, p = X.shape

    W = _sym_decorrelation(w_init)

    # we set lim to tol+1 to be sure to enter at least once in next while
    lim = tol + 1 
    it = 0
    while ((lim > tol) and (it < (maxit-1))):
        wtx = np.dot(W, X)
        gwtx = g(wtx, fun_args)
        g_wtx = gprime(wtx, fun_args)
        W1 = np.dot(gwtx, X.T)/float(p) - np.dot(np.diag(g_wtx.mean(axis=1)), W)
 
        W1 = _sym_decorrelation(W1)
        
        lim = max(abs(abs(np.diag(np.dot(W1, W.T))) - 1))
        W = W1
        it += 1

    return W


def fastica(X, n_comp=None,
            algorithm="parallel", whiten=True, fun="logcosh", fun_prime='', 
            fun_args={}, maxit=200, tol=1e-04, w_init=None):
    """Perform Fast Independent Component Analysis.

    Parameters
    ----------
    X : (p, n) array
        Array with n observations (statistical units) measured on p variables.
    n_comp : int, optional
        Number of components to extract. If None no dimension reduction
        is performed.
    algorithm : {'parallel','deflation'}
        Apply an parallel or deflational FASTICA algorithm.
    whiten: boolean, optional
        If true perform an initial whitening of the data. Do not set to 
        false unless the data is already white, as you will get incorrect 
        results.
        If whiten is true, the data is assumed to have already been
        preprocessed: it should be centered, normed and white.
    fun : String or Function
          The functional form of the G function used in the
          approximation to neg-entropy. Could be either 'logcosh', 'exp', 
          or 'cube'.
          You can also provide your own function but in this case, its 
          derivative should be provided via argument fun_prime
    fun_prime : Empty string ('') or Function
                See fun.
    fun_args : Optional dictionnary
               If empty and if fun='logcosh', fun_args will take value 
               {'alpha' : 1.0}
    maxit : int
            Maximum number of iterations to perform
    tol : float
          A positive scalar giving the tolerance at which the
          un-mixing matrix is considered to have converged
    w_init : (n_comp,n_comp) array
             Initial un-mixing array of dimension (n.comp,n.comp).
             If None (default) then an array of normal r.v.'s is used
 
    Results
    -------
    K : (n_comp, p) array
        pre-whitening matrix that projects data onto th first n.comp
        principal components. Returned only if whiten is True
    W : (n_comp, n_comp) array
        estimated un-mixing matrix
        The mixing matrix can be obtained by::
            w = np.asmatrix(W) * K.T
            A = w.T * (w * w.T).I
    S : (n_comp, n) array
        estimated source matrix


    Notes
    -----

    The data matrix X is considered to be a linear combination of
    non-Gaussian (independent) components i.e. X = SA where columns of S
    contain the independent components and A is a linear mixing
    matrix. In short ICA attempts to `un-mix' the data by estimating an
    un-mixing matrix W where S = W K X.

    Implemented using FastICA:

      A. Hyvarinen and E. Oja, Independent Component Analysis:
      Algorithms and Applications, Neural Networks, 13(4-5), 2000,
      pp. 411-430

    """
    algorithm_funcs = {'parallel': _ica_par,
                       'deflation': _ica_def}

    alpha = fun_args.get('alpha',1.0)
    if (alpha < 1) or (alpha > 2):
        raise ValueError("alpha must be in [1,2]")

    if type(fun) is types.StringType:
        # Some standard nonlinear functions
        # XXX: these should be optimized, as they can be a bottleneck.
        if fun == 'logcosh':
            def g(x, fun_args):
                alpha = fun_args.get('alpha', 1.0)
                return np.tanh(alpha * x)
            def gprime(x, fun_args):
                alpha = fun_args.get('alpha', 1.0)
                return alpha * (1 - (np.tanh(alpha * x))**2)
        elif fun == 'exp':
            def g(x, fun_args):
                return x * np.exp(-(x**2)/2)
            def gprime(x, fun_args):
                return (1 - x**2) * np.exp(-(x**2)/2)
        elif fun == 'cube':
            def g(x, fun_args):
                return x**3
            def gprime(x, fun_args):
                return 3*x**2
        else:
            raise ValueError(
                        'fun argument should be one of logcosh, exp or cube')
    elif callable(fun):
        raise ValueError('fun argument should be either a string '
                         '(one of logcosh, exp or cube) or a function') 
    else:
        def g(x, fun_args):
            return fun(x, **fun_args)
        def gprime(x, fun_args):
            return fun_prime(x, **fun_args)

    p, n = X.shape

    if n_comp is None:
        n_comp = min(n, p)
    if (n_comp > min(n, p)):
        n_comp = min(n, p)
        print("n_comp is too large: it will be set to %s" % n_comp)


    if whiten:
        # Centering the columns (ie the variables)
        X = X - X.mean(axis=-1)[:, np.newaxis]

        # Whitening and preprocessing by PCA
        u, d, _ = linalg.svd(X, full_matrices=False)
        del _
        K = (u/d).T[:n_comp]  # see (6.33) p.140
        del u, d
        X1 = np.dot(K, X) # see (13.6) p.267 Here X1 is white and data 
        # in X has been projected onto a subspace by PCA
    else:
        X1 = X.copy()
    X1 *= np.sqrt(n)

    if w_init is None:
        w_init = np.random.normal(size=(n_comp, n_comp))
    else:
        w_init = np.asarray(w_init)
        if w_init.shape != (n_comp,n_comp):
            raise ValueError("w_init has invalid shape -- should be %(shape)s"
                             % {'shape': (n_comp,n_comp)})

    kwargs = {'tol': tol,
              'g': g,
              'gprime': gprime,
              'fun_args': fun_args,
              'maxit': maxit,
              'w_init': w_init}

    func = algorithm_funcs.get(algorithm, 'parallel')

    W = func(X1, **kwargs)
    del X1

    if whiten:
        S = np.dot(np.dot(W, K), X)
        return K, W, S
    else:
        S = np.dot(W, X)
        return W, S


