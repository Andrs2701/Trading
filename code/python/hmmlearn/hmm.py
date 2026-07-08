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
        for i in range(k):
            cov = self.covars_[i]
            cov = 0.5 * (cov + cov.T) + self.min_covar * np.eye(n_features)
            # Use multivariate_normal logpdf
            log_b[:, i] = multivariate_normal.logpdf(X, mean=self.means_[i], cov=cov, allow_singular=True)
        return log_b

    def _forward(self, log_b):
        n_samples, k = log_b.shape
        log_alpha = np.zeros((n_samples, k))
        
        log_startprob = np.log(np.maximum(self.startprob_, 1e-30))
        log_transmat = np.log(np.maximum(self.transmat_, 1e-30))
        
        log_alpha[0] = log_startprob + log_b[0]
        for t in range(1, n_samples):
            for j in range(k):
                log_alpha[t, j] = log_b[t, j] + logsumexp(log_alpha[t-1] + log_transmat[:, j])
        return log_alpha

    def _backward(self, log_b):
        n_samples, k = log_b.shape
        log_beta = np.zeros((n_samples, k))
        
        log_transmat = np.log(np.maximum(self.transmat_, 1e-30))
        
        for t in range(n_samples - 2, -1, -1):
            for i in range(k):
                log_beta[t, i] = logsumexp(log_transmat[i, :] + log_b[t+1, :] + log_beta[t+1, :])
        return log_beta

    def fit(self, X, lengths=None):
        self._init_params(X)
        
        last_logprob = -np.inf
        for it in range(self.n_iter):
            log_b = self._compute_log_likelihoods(X)
            log_alpha = self._forward(log_b)
            log_beta = self._backward(log_b)
            
            log_prob = logsumexp(log_alpha[-1])
            
            if it > 0 and log_prob - last_logprob < self.tol:
                break
            last_logprob = log_prob
            
            # E-step
            log_gamma = log_alpha + log_beta
            log_gamma -= logsumexp(log_gamma, axis=1, keepdims=True)
            gamma = np.exp(log_gamma)
            
            n_samples, k = X.shape[0], self.n_components
            log_transmat = np.log(np.maximum(self.transmat_, 1e-30))
            
            log_xi = np.zeros((n_samples - 1, k, k))
            for t in range(n_samples - 1):
                for i in range(k):
                    for j in range(k):
                        log_xi[t, i, j] = log_alpha[t, i] + log_transmat[i, j] + log_b[t+1, j] + log_beta[t+1, j]
                log_xi[t] -= logsumexp(log_xi[t])
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
        return logsumexp(log_alpha[-1])

    def predict_proba(self, X, lengths=None):
        log_b = self._compute_log_likelihoods(X)
        log_alpha = self._forward(log_b)
        log_beta = self._backward(log_b)
        log_gamma = log_alpha + log_beta
        log_gamma -= logsumexp(log_gamma, axis=1, keepdims=True)
        return np.exp(log_gamma)
