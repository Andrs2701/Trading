import numpy as np
import math
from scipy.special import logsumexp
from scipy.stats import multivariate_normal
from sklearn.cluster import KMeans

class GaussianHMM:
    def __init__(self, n_components=1, covariance_type='full', n_iter=100, tol=1e-2, random_state=None):
        self.n_components = n_components
        self.covariance_type = covariance_type
        self.n_iter = n_iter
        self.tol = tol
        self.random_state = random_state
        self.min_covar = 1e-3
        
        self.startprob_ = None
        self.transmat_ = None
        self.means_ = None
        self.covars_ = None
        
    def _init_params(self, X):
        k = self.n_components
        n_samples, n_features = X.shape
        
        # Initialize means using KMeans
        kmeans = KMeans(n_clusters=k, random_state=self.random_state, n_init='auto')
        kmeans.fit(X)
        self.means_ = kmeans.cluster_centers_
        
        # Initialize covariances to empirical covariance
        self.covars_ = np.zeros((k, n_features, n_features))
        total_cov = np.cov(X.T) if n_samples > 1 else np.eye(n_features)
        total_cov += self.min_covar * np.eye(n_features)
        for i in range(k):
            self.covars_[i] = total_cov.copy()
            
        # Initialize startprob and transmat to uniform
        self.startprob_ = np.full(k, 1.0 / k)
        self.transmat_ = np.full((k, k), 1.0 / k)

    def _compute_log_likelihoods(self, X):
        n_samples, n_features = X.shape
        k = self.n_components
        log_b = np.zeros((n_samples, k))
        log_2pi = np.log(2.0 * np.pi)
        for i in range(k):
            cov = self.covars_[i]
            cov = 0.5 * (cov + cov.T) + self.min_covar * np.eye(n_features)
            try:
                L = np.linalg.cholesky(cov)
                diff = X - self.means_[i]
                y = np.linalg.solve(L, diff.T)
                quad_term = np.sum(y**2, axis=0)
                log_det = 2.0 * np.sum(np.log(np.diag(L)))
                log_b[:, i] = -0.5 * (n_features * log_2pi + log_det + quad_term)
            except np.linalg.LinAlgError:
                diag = np.diag(cov)
                diff = X - self.means_[i]
                quad_term = np.sum((diff**2) / diag, axis=1)
                log_det = np.sum(np.log(diag))
                log_b[:, i] = -0.5 * (n_features * log_2pi + log_det + quad_term)
        return log_b

    def _forward(self, log_b):
        n_samples, k = log_b.shape
        log_alpha = np.zeros((n_samples, k))
        
        log_startprob = np.log(np.maximum(self.startprob_, 1e-30))
        log_transmat = np.log(np.maximum(self.transmat_, 1e-30))
        
        log_alpha[0] = log_startprob + log_b[0]
        for t in range(1, n_samples):
            a = log_alpha[t-1][:, np.newaxis] + log_transmat
            a_max = np.max(a, axis=0)
            log_alpha[t] = log_b[t] + a_max + np.log(np.sum(np.exp(a - a_max), axis=0))
        return log_alpha

    def _backward(self, log_b):
        n_samples, k = log_b.shape
        log_beta = np.zeros((n_samples, k))
        
        log_transmat = np.log(np.maximum(self.transmat_, 1e-30))
        
        for t in range(n_samples - 2, -1, -1):
            a = log_transmat + log_b[t+1][np.newaxis, :] + log_beta[t+1][np.newaxis, :]
            a_max = np.max(a, axis=1)
            log_beta[t] = a_max + np.log(np.sum(np.exp(a - a_max[:, np.newaxis]), axis=1))
        return log_beta

    def fit(self, X, lengths=None):
        if self.means_ is None:
            self._init_params(X)
        
        last_logprob = -np.inf
        for it in range(self.n_iter):
            log_b = self._compute_log_likelihoods(X)
            log_alpha = self._forward(log_b)
            log_beta = self._backward(log_b)
            
            a = log_alpha[-1]
            a_max = np.max(a)
            log_prob = a_max + np.log(np.sum(np.exp(a - a_max)))
            
            if it > 0 and log_prob - last_logprob < self.tol:
                break
            last_logprob = log_prob
            
            # E-step
            log_gamma = log_alpha + log_beta
            log_gamma_max = np.max(log_gamma, axis=1, keepdims=True)
            log_gamma -= log_gamma_max + np.log(np.sum(np.exp(log_gamma - log_gamma_max), axis=1, keepdims=True))
            gamma = np.exp(log_gamma)
            
            n_samples, k = X.shape[0], self.n_components
            log_transmat = np.log(np.maximum(self.transmat_, 1e-30))
            
            # Vectorized computation of log_xi
            log_xi = (log_alpha[:-1, :, np.newaxis] 
                      + log_transmat[np.newaxis, :, :] 
                      + log_b[1:, np.newaxis, :] 
                      + log_beta[1:, np.newaxis, :])
            log_xi_max = np.max(log_xi, axis=(1, 2), keepdims=True)
            log_xi -= log_xi_max + np.log(np.sum(np.exp(log_xi - log_xi_max), axis=(1, 2), keepdims=True))
            xi = np.exp(log_xi)
            
            # M-step
            self.startprob_ = gamma[0] / gamma[0].sum()
            
            sum_xi = xi.sum(axis=0)
            sum_gamma = gamma[:-1].sum(axis=0)[:, np.newaxis]
            self.transmat_ = np.where(sum_gamma > 0, sum_xi / sum_gamma, 1.0 / k)
            self.transmat_ /= self.transmat_.sum(axis=1, keepdims=True)
            
            for i in range(k):
                weight = gamma[:, i]
                sum_w = weight.sum()
                if sum_w > 0:
                    self.means_[i] = (X * weight[:, np.newaxis]).sum(axis=0) / sum_w
                    
                    diff = X - self.means_[i]
                    cov = np.dot(diff.T, diff * weight[:, np.newaxis]) / sum_w
                    self.covars_[i] = cov + self.min_covar * np.eye(X.shape[1])
                else:
                    self.covars_[i] = np.eye(X.shape[1]) * self.min_covar
                    
        return self

    def score(self, X, lengths=None):
        log_b = self._compute_log_likelihoods(X)
        log_alpha = self._forward(log_b)
        a = log_alpha[-1]
        a_max = np.max(a)
        return a_max + np.log(np.sum(np.exp(a - a_max)))

    def predict_proba(self, X, lengths=None):
        log_b = self._compute_log_likelihoods(X)
        log_alpha = self._forward(log_b)
        log_beta = self._backward(log_b)
        log_gamma = log_alpha + log_beta
        log_gamma_max = np.max(log_gamma, axis=1, keepdims=True)
        log_gamma -= log_gamma_max + np.log(np.sum(np.exp(log_gamma - log_gamma_max), axis=1, keepdims=True))
        return np.exp(log_gamma)
