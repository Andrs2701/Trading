import time
import numpy as np
from scipy.special import logsumexp
from scipy.stats import multivariate_normal

# Simple HMM class to profile
class ProfileHMM:
    def __init__(self):
        self.k = 5
        self.means = np.random.randn(5, 3)
        self.covars = np.array([np.eye(3) for _ in range(5)])
        self.startprob = np.full(5, 0.2)
        self.transmat = np.full((5, 5), 0.2)
        self.min_covar = 1e-3
        
    def log_likelihood_scipy(self, X):
        log_b = np.zeros((X.shape[0], self.k))
        for i in range(self.k):
            cov = self.covars[i]
            log_b[:, i] = multivariate_normal.logpdf(X, mean=self.means[i], cov=cov)
        return log_b

    def log_likelihood_cholesky(self, X):
        log_b = np.zeros((X.shape[0], self.k))
        log_2pi = np.log(2.0 * np.pi)
        n_features = X.shape[1]
        for i in range(self.k):
            cov = self.covars[i]
            L = np.linalg.cholesky(cov)
            diff = X - self.means[i]
            y = np.linalg.solve(L, diff.T)
            quad_term = np.sum(y**2, axis=0)
            log_det = 2.0 * np.sum(np.log(np.diag(L)))
            log_b[:, i] = -0.5 * (n_features * log_2pi + log_det + quad_term)
        return log_b

    def log_likelihood_inv(self, X):
        log_b = np.zeros((X.shape[0], self.k))
        log_2pi = np.log(2.0 * np.pi)
        n_features = X.shape[1]
        for i in range(self.k):
            cov = self.covars[i]
            inv_cov = np.linalg.inv(cov)
            diff = X - self.means[i]
            quad_term = np.sum(np.dot(diff, inv_cov) * diff, axis=1)
            sign, log_det = np.linalg.slogdet(cov)
            log_b[:, i] = -0.5 * (n_features * log_2pi + log_det + quad_term)
        return log_b

    def forward_scipy(self, log_b):
        n_samples, k = log_b.shape
        log_alpha = np.zeros((n_samples, k))
        log_startprob = np.log(self.startprob)
        log_transmat = np.log(self.transmat)
        log_alpha[0] = log_startprob + log_b[0]
        for t in range(1, n_samples):
            log_alpha[t] = log_b[t] + logsumexp(log_alpha[t-1][:, np.newaxis] + log_transmat, axis=0)
        return log_alpha

    def forward_numpy(self, log_b):
        n_samples, k = log_b.shape
        log_alpha = np.zeros((n_samples, k))
        log_startprob = np.log(self.startprob)
        log_transmat = np.log(self.transmat)
        log_alpha[0] = log_startprob + log_b[0]
        for t in range(1, n_samples):
            # Inline custom logsumexp to avoid scipy overhead
            a = log_alpha[t-1][:, np.newaxis] + log_transmat
            a_max = np.max(a, axis=0)
            log_alpha[t] = log_b[t] + a_max + np.log(np.sum(np.exp(a - a_max), axis=0))
        return log_alpha

if __name__ == "__main__":
    X = np.random.randn(750, 3)
    hmm = ProfileHMM()
    
    # 1. Profile Likelihoods
    t0 = time.time()
    for _ in range(100):
        hmm.log_likelihood_scipy(X)
    print("Scipy likelihood (100 runs):", time.time() - t0)

    t0 = time.time()
    for _ in range(100):
        hmm.log_likelihood_cholesky(X)
    print("Cholesky likelihood (100 runs):", time.time() - t0)

    t0 = time.time()
    for _ in range(100):
        hmm.log_likelihood_inv(X)
    print("Inv likelihood (100 runs):", time.time() - t0)

    # 2. Profile Forward Pass
    log_b = hmm.log_likelihood_inv(X)
    t0 = time.time()
    for _ in range(100):
        hmm.forward_scipy(log_b)
    print("Scipy forward (100 runs):", time.time() - t0)

    t0 = time.time()
    for _ in range(100):
        hmm.forward_numpy(log_b)
    print("Numpy forward (100 runs):", time.time() - t0)
