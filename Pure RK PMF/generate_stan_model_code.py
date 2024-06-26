'''
Function file to create a valid stan model such 
that the variances are in increasing order for
the Hybrid model
'''

def generate_stan_code(include_clusters=False, variance_known=False, variance_MC_known=False):
    # include_clusters: whether to include cluster data
    #                 : If true include number of cluster, cluster 
    #                   assignment as a matrix, and the within cluster varaince 
    #                   (vector for each cluster) as inputs to the model
    # variance_known: whether the data-model variance is known
    #               : If true include the data-model variance as input to the model

    model_code = '''
    functions {
        // kernel for composition
        matrix Kx(vector x1, vector x2, int order) {
            int N = rows(x1);
            int M = rows(x2);
            matrix[N, order+1] X1;
            matrix[M, order+1] X2;
            for (i in 1:order) {
                X1[:,i] = x1 .^(order+2-i) - x1;
                X2[:,i] = x2 .^(order+2-i) - x2;
            }
            X1[:,order+1] = 1e-1 * x1 .* sqrt(1-x1) .* exp(x1);
            X2[:,order+1] = 1e-1 * x2 .* sqrt(1-x2) .* exp(x2);
            return X1 * X2';
        }

        // kernel for Temperature
        matrix KT(vector T1, vector T2) {
            int N = rows(T1);
            int M = rows(T2);
            matrix[N, 4] TT1 = append_col(append_col(append_col(rep_vector(1.0, N), T1), T1.^2), 1e-3 * T1.^3);
            matrix[M, 4] TT2 = append_col(append_col(append_col(rep_vector(1.0, M), T2), T2.^2), 1e-3 * T2.^3);

            return TT1 * TT2';
        }

        // Combined kernel
        matrix Kernel(vector x1, vector x2, vector T1, vector T2, int order) {
            return Kx(x1, x2, order) .* KT(T1, T2); 
        }'''
    if include_clusters:
        model_code += '''
        // functions for the priors of the feature matrices and means thereof
        real ps_feature_matrices(array[] int M_slice, int start, int end, array[] matrix U_raw_means,
          array[] matrix V_raw_means, array[] matrix U_raw, array[] matrix V_raw, vector E_cluster, matrix C) {
            real all_target = 0;
            for (m in start:end) {
                all_target += std_normal_lpdf(to_vector(U_raw_means[m]));
                all_target += std_normal_lpdf(to_vector(V_raw_means[m]));
                all_target += normal_lpdf(to_vector(U_raw[m]) | to_vector(U_raw_means[m]*C), E_cluster);
                all_target += normal_lpdf(to_vector(V_raw[m]) | to_vector(U_raw_means[m]*C), E_cluster);
            }
            return all_target;
          }
        '''
    else:
        model_code += '''
        // functions for the priors of the feature matrices
        real ps_feature_matrices(array[] int M_slice, int start, int end, array[] matrix U_raw, 
          array[] matrix V_raw) {
            real all_target = 0;
            for (m in start:end) {
                all_target += std_normal_lpdf(to_vector(U_raw[m]));
                all_target += std_normal_lpdf(to_vector(V_raw[m]));
            }
            return all_target;
          }'''
    model_code += '''
        // function for the likelihood and prior on smoothed values
        real ps_like(array[] int N_slice, int start, int end, vector y, matrix cov_y_yMC,
          matrix mu_y_y_MC, matrix L_y_MC_inv_cov, matrix y_MC_prec, vector v,
          array[,] int Idx_all, int M, int N_T, int N_MC, int N_C, int N_known, array[] int N_points,
          vector v_ARD, array[,] matrix U_raw, array[,] matrix V_raw, real v_MC, matrix K_MC) {
            real all_target = 0;
            for (i in start:end) {
                vector[N_MC] y_MC_pred;
                for(t in 1:N_T) {
                    for (m in 1:M-1) {
                        y_MC_pred[m+N_C*(t-1)] = dot_product(U_raw[t,m,:,Idx_all[i,1]] .* v_ARD, V_raw[t,m,:,Idx_all[i,2]]);
                        y_MC_pred[N_C-m+1+N_C*(t-1)] = dot_product(U_raw[t,m,:,Idx_all[i,2]] .* v_ARD, V_raw[t,m,:,Idx_all[i,1]]); 
                    }
                    y_MC_pred[M+N_C*(t-1)] = dot_product(U_raw[t,M,:,Idx_all[i,1]] .* v_ARD, U_raw[t,M,:,Idx_all[i,2]]);
                }
                all_target += -0.5 * dot_self(L_y_MC_inv_cov * y_MC_pred); // GP prior

                if (i <= N_known) {'''
    if not variance_MC_known:
        model_code += '''
                    vector[N_points[i]] y_pred = ( mu_y_y_MC[sum(N_points[:i-1])+1:sum(N_points[:i]),:] * y_MC_prec) * y_MC_pred;
                    matrix[N_points[i], N_points[i]] stable_inv; 
                    {
                        matrix[N_points[i], N_MC] ss = mu_y_y_MC[sum(N_points[:i-1])+1:sum(N_points[:i]),:] * L_y_MC_inv_cov';
                        stable_inv = ss * ss';
                        stable_inv = (stable_inv + stable_inv')/2.0; // insure symmetry
                    }
                    matrix[N_points[i], N_points[i]] cov_y = cov_y_yMC[sum(N_points[:i-1])+1:sum(N_points[:i]), :N_points[i]] - stable_inv;'''
        if not variance_known:
            model_code += '''
                    cov_y = add_diag(cov_y, v[i]);'''
    else: 
        model_code += '''
                    vector[N_points[i]] y_pred = mu_y_y_MC[sum(N_points[:i-1])+1:sum(N_points[:i]),:] * y_MC_pred;'''
    if not variance_known and variance_MC_known:
        model_code += '''
                    matrix[N_points[i], N_points[i]] cov_y = add_diag(cov_y_yMC[sum(N_points[:i-1])+1:sum(N_points[:i]), :N_points[i]], v[i]);'''
    if variance_known and variance_MC_known:
        model_code += '''
                    matrix[N_points[i], N_points[i]] cov_y = cov_y_yMC[sum(N_points[:i-1])+1:sum(N_points[:i]), :N_points[i]];'''
    model_code += '''
                    all_target += multi_normal_lpdf(y[sum(N_points[:i-1])+1:sum(N_points[:i])] | y_pred, cov_y);
                }
            }
            return all_target;
          }
    }

    data {
        int N_known;                        // number of known mixtures
        int N_unknown;                      // number of unknown mixtures
        array[N_known] int N_points;        // number of experimental points per known dataset
        int order;                          // order of the compositional polynomial
        vector[sum(N_points)] x1;           // experimental composition
        vector[sum(N_points)] T1;           // experimental temperatures
        vector[sum(N_points)] y1;           // experimental excess enthalpy
        int N_T;                            // number of interpolated temperatures
        int N_C;                            // number of interpolated compositions
        vector[N_T] T2_int;                 // unique temperatures to interpolate
        vector[N_C] x2_int;                 // unique compositions to interpolate
        real<lower=0> scale_lower;          // lower bound for scale parameter'''
    if variance_MC_known:
        model_code += '''
        real<lower=0> v_MC;                 // error between of y_MC and (U,V)'''
    model_code += '''
        int grainsize;                      // number of grainsizes

        int N;                              // number of components
        int D;                              // rank of feature matrices
        array[N_known, 2] int Idx_known;    // indices (row, column) of known datasets
        array[N_unknown, 2] int Idx_unknown;// indices (row, column) of unknown datasets
        
        real<lower=0> jitter;               // jitter for stability of covariances'''
    if variance_known: # include known data-model variance data input
        model_code += '''
        vector<lower=0>[N_known] v;         // known data-model variance'''

    if include_clusters: # include cluster data input
        model_code += '''   
        int K;                              // number of clusters
        matrix[K, N] C;                     // cluster assignment
        vector<lower=0>[K] v_cluster;       // within cluster variance'''

    model_code += '''
    }

    transformed data {
        real error = 0.01;                                      // error in the data (fraction of experimental data)
        vector[sum(N_points)] var_data = square(error*y1);      // variance of the data
        int M = (N_C + 1) %/% 2;                                // interger division to get the number of U matrices
        int N_MC = N_C*N_T;                                     // overall number of interpolated datapoints per dataset
        array[M-1] int M_slice;                                 // array of integers to be used as indices in parallel computations
        array[N_known+N_unknown] int N_slice;                   // array of integers to be used as indices in parallel computations
        array[N_known+N_unknown,2] int Idx_all = append_array(Idx_known, Idx_unknown); // indices of all datasets
        vector[N_MC] x2;                                        // concatnated vector of x2_int
        vector[N_MC] T2;                                        // concatenated vector of T2_int
        matrix[N_MC, N_MC] K_MC;                                // kernel for the interpolated data
        matrix[sum(N_points), N_MC] mu_y_y_MC;                  // Mapping from y_MC to y (predictive GP mean)
        matrix[sum(N_points), max(N_points)] cov_y_yMC;         // covariance of y smmooth|y_MC'''
    if variance_MC_known:
        model_code += '''
        matrix[N_MC, N_MC] y_MC_prec;                           // inverse of kernel
        matrix[N_MC, N_MC] L_y_MC_inv_cov;                      // Inverse of cholesky decomposition of K_MC'''
    if include_clusters: # transform cluster variance parameters into a vector for easier processing
        model_code += '''
        vector[D*N] E_cluster = to_vector((rep_matrix(v_cluster', D) * C)); // within cluster varaince matrix'''
    
    model_code += '''
        matrix[N_MC, N_MC] cov_y_MC;                            // conditional covariance of y_MC|(U,V)
        // Assign MC input vectors for temperature and composition
        for (i in 1:N_T) {
            x2[(i-1)*N_C+1:i*N_C] = x2_int;
            T2[(i-1)*N_C+1:i*N_C] = rep_vector(T2_int[i],N_C);
        } 

        // Assign MC kernel
        K_MC = add_diag(Kernel(x2, x2, T2, T2, order), jitter);'''

    if variance_MC_known:
        model_code += '''
        
        L_y_MC_inv_cov = inverse(cholesky_decompose(add_diag(K_MC, v_MC)));
        y_MC_prec = crossprod(L_y_MC_inv_cov);         // L_MC_inv' * L_MC_inv

        {
            // Loop through data sets to compute the relevant matrix, mapping from y_MC to y and covariance
            for (i in 1:N_known) {
                // obtain kernel matrix for cross covariance
                matrix[N_points[i], N_MC] K_y_yMC = Kernel(x1[sum(N_points[:i-1])+1:sum(N_points[:i])], 
                                                        x2, 
                                                        T1[sum(N_points[:i-1])+1:sum(N_points[:i])], 
                                                        T2, order); 

                // Stable implementation of A*B*A^T where B is a positive semi-definite matrix
                // This is decomposed into A*(L^-1)^T*L^-1*A^T where L is the cholesky factor of B
                // A*B*A^T = C*C^T where C = A*(L^-1)^T

                // Computation of above mentioned K12*K22^-1*K12^T
                matrix[N_points[i], N_points[i]] stable_inv;
                {
                    matrix[N_points[i], N_MC] ss = K_y_yMC * L_y_MC_inv_cov';
                    stable_inv = ss * ss';
                    stable_inv = (stable_inv + stable_inv')/2.0; // insure symmetry
                }
                
                // obtain kernel for the data
                matrix[N_points[i], N_points[i]] K_y = Kernel(x1[sum(N_points[:i-1])+1:sum(N_points[:i])], 
                                                            x1[sum(N_points[:i-1])+1:sum(N_points[:i])], 
                                                            T1[sum(N_points[:i-1])+1:sum(N_points[:i])], 
                                                            T1[sum(N_points[:i-1])+1:sum(N_points[:i])], order);
                // Mapping from y_MC to y
                mu_y_y_MC[sum(N_points[:i-1])+1:sum(N_points[:i]), :] = K_y_yMC * y_MC_prec;
                // Computation of K12*K22^-1*K12^T
                cov_y_yMC[sum(N_points[:i-1])+1:sum(N_points[:i]), :N_points[i]] = add_diag(K_y, var_data[sum(N_points[:i-1])+1:sum(N_points[:i])]) - stable_inv;'''
    
    else:
        model_code += '''

        {
            // Loop through data sets to compute the relevant matrix, mapping from y_MC to y and covariance
            for (i in 1:N_known) {
                // obtain kernel matrix for cross covariance
                matrix[N_points[i], N_MC] K_y_yMC = Kernel(x1[sum(N_points[:i-1])+1:sum(N_points[:i])], 
                                                        x2, 
                                                        T1[sum(N_points[:i-1])+1:sum(N_points[:i])], 
                                                        T2, order); 

                // Stable implementation of A*B*A^T where B is a positive semi-definite matrix
                // This is decomposed into A*(L^-1)^T*L^-1*A^T where L is the cholesky factor of B
                // A*B*A^T = C*C^T where C = A*(L^-1)^T

                // Computation of above mentioned K12*K22^-1*K12^T
                // obtain kernel for the data
                matrix[N_points[i], N_points[i]] K_y = Kernel(x1[sum(N_points[:i-1])+1:sum(N_points[:i])], 
                                                            x1[sum(N_points[:i-1])+1:sum(N_points[:i])], 
                                                            T1[sum(N_points[:i-1])+1:sum(N_points[:i])], 
                                                            T1[sum(N_points[:i-1])+1:sum(N_points[:i])], order);
                // Mapping from y_MC to y
                mu_y_y_MC[sum(N_points[:i-1])+1:sum(N_points[:i]), :] = K_y_yMC ;
                // Computation of K12*K22^-1*K12^T
                cov_y_yMC[sum(N_points[:i-1])+1:sum(N_points[:i]), :N_points[i]] = add_diag(K_y, var_data[sum(N_points[:i-1])+1:sum(N_points[:i])]);'''    
    if variance_known:
            model_code += '''
                // Add variance on diagonal
                cov_y_yMC[sum(N_points[:i-1])+1:sum(N_points[:i]), :N_points[i]] = add_diag(cov_y_yMC[sum(N_points[:i-1])+1:sum(N_points[:i]), :N_points[i]], v[i]);'''

    model_code += '''    
            }
        }

        for ( i in 1:N_known+N_unknown) {        
            // slice variable for parallel computations
            N_slice[i] = i;
        }

        // Slice variables for feature matrices
        M_slice = N_slice[:M-1];
    }

    parameters {'''

    if not variance_known: # include data-model variance as parameter to model
        model_code += '''
        vector<lower=0, upper=5>[N_known] v;        // data-model variance; constrained'''

    if not variance_MC_known: # include MC variance as parameter to model
        model_code += '''
        real<lower=0, upper=5> v_MC;                // error between of y_MC and (U,V); constrained'''

    if include_clusters: # include cluster means as parameters
        model_code += '''
        array[N_T, M] matrix[D,K] U_raw_means;      // U_raw cluster means
        array[N_T, M-1] matrix[D,K] V_raw_means;    // V_raw cluster means'''

    model_code += '''
        array[N_T, M] matrix[D,N] U_raw;            // feature matrices U
        array[N_T, M-1] matrix[D,N] V_raw;          // feature matrices V
        real<lower=0, upper=scale_lower> scale;     // scale dictating the strenght of ARD effect
        vector<lower=0>[D] v_ARD;                   // ARD variances on decorrelated prior
    }
    
    model {'''
    if not variance_MC_known:
        model_code += '''
        // Inverse cholesky factor of MC covariance
        matrix[N_MC, N_MC] L_y_MC_inv_cov = inverse(cholesky_decompose(add_diag(K_MC, v_MC)));
        // Precision matrix of MC
        matrix[N_MC, N_MC] y_MC_prec = crossprod(L_y_MC_inv_cov);         // L_MC_inv' * L_MC_inv

        // add addjustment for v_MC
        target += (N_known + N_unknown) * log_determinant(L_y_MC_inv_cov);
        '''    
    model_code +='''     
        // Gamma prior for scale
        scale ~ exponential(5);

        // Exponential prior on ARD variances
        v_ARD ~ exponential(1/scale);
    '''

    if not variance_known: # include data-model variance as parameter prior to model
        model_code += '''
        // Exponential prior for variance-model mismatch
        v ~ exponential(1);
        '''

    if not variance_MC_known: # include MC variance as parameter prior to model
        model_code += '''
        // inverse gamma prior for the error between the reconstructions and smoothed values
        v_MC ~ exponential(1);
        '''

    if include_clusters: # include cluster mean priors
        model_code += '''
        // priors for cluster means and feature matrices 
        for (t in 1:N_T) {
            target += reduce_sum(ps_feature_matrices, M_slice, grainsize, U_raw_means[t,:],
                        V_raw_means[t,:], U_raw[t,:M-1], V_raw[t,:M-1], E_cluster, C);
            to_vector(U_raw_means[t,M,:,:]) ~ std_normal();
            to_vector(U_raw[t,M,:,:]) ~ normal(to_vector(U_raw_means[t,M,:,:]*C), E_cluster);
        }
        '''
    else: # exclude cluster parameters 
        model_code += '''
        // priors for feature matrices
        for (t in 1:N_T) {
            target += reduce_sum(ps_feature_matrices, M_slice, grainsize, U_raw[t,:M-1], 
                        V_raw[t,:]);
            to_vector(U_raw[t,M,:,:]) ~ std_normal();
        }
        '''

    model_code += '''
        // Likelihood function
        target += reduce_sum(ps_like, N_slice, grainsize, y1, cov_y_yMC,
                        mu_y_y_MC, L_y_MC_inv_cov, y_MC_prec, v,
                        Idx_all, M, N_T, N_MC, N_C, N_known, N_points,
                        v_ARD, U_raw, V_raw, v_MC, K_MC);
    }

    generated quantities {
        vector[sum(N_points)] y_pred;
        vector[N_known] log_lik;
        matrix[N_MC, N_known+N_unknown] y_MC_pred;
        for (i in 1:N_known) {'''
    if not variance_MC_known:
        model_code += '''
            // Inverse cholesky factor of MC covariance
            matrix[N_MC, N_MC] L_y_MC_inv_cov = inverse(cholesky_decompose(add_diag(K_MC, v_MC)));
            // Precision matrix of MC
            matrix[N_MC, N_MC] y_MC_prec = crossprod(L_y_MC_inv_cov);         // L_MC_inv' * L_MC_inv
            // Stable computation of covariance
            matrix[N_points[i], N_MC] stable_inv = mu_y_y_MC[sum(N_points[:i-1])+1:sum(N_points[:i]),:] * L_y_MC_inv_cov'; 
            // Compute K2 - K21*K1^-1*K21^T
            matrix[N_points[i], N_points[i]] cov_y = cov_y_yMC[sum(N_points[:i-1])+1:sum(N_points[:i]), :N_points[i]] - stable_inv * stable_inv';'''
    
        if not variance_known:
            model_code += '''
            // Add variance on diagonal cov_y = K2 - K21*K1^-1*K21^T + v2*I
            cov_y = add_diag(cov_y, v[i]);'''

    else:
        model_code += '''
            // Copy covariance matrix
            matrix[N_points[i], N_points[i]] cov_y = cov_y_yMC[sum(N_points[:i-1])+1:sum(N_points[:i]), :N_points[i]];'''

    if not variance_known and variance_MC_known:
        model_code += '''
            // Add variance on diagonal
            cov_y = add_diag(cov_y_yMC[sum(N_points[:i-1])+1:sum(N_points[:i]), :N_points[i]], v[i]);'''

    model_code += '''
            for(t in 1:N_T) {
                for (m in 1:M-1) {
                    y_MC_pred[m+N_C*(t-1), i] = dot_product(U_raw[t,m,:,Idx_all[i,1]] .* v_ARD, V_raw[t,m,:,Idx_all[i,2]]);
                    y_MC_pred[N_C-m+1+N_C*(t-1), i] = dot_product(U_raw[t,m,:,Idx_all[i,2]] .* v_ARD, V_raw[t,m,:,Idx_all[i,1]]); 
                }
                y_MC_pred[M+N_C*(t-1), i] = dot_product(U_raw[t,M,:,Idx_all[i,1]] .* v_ARD, U_raw[t,M,:,Idx_all[i,2]]);
            }'''

    if variance_MC_known:
        model_code += '''
            y_pred[sum(N_points[:i-1])+1:sum(N_points[:i])] = mu_y_y_MC[sum(N_points[:i-1])+1:sum(N_points[:i]),:] * y_MC_pred[:, i];'''

    else:
        model_code += '''
            y_pred[sum(N_points[:i-1])+1:sum(N_points[:i])] = ( mu_y_y_MC[sum(N_points[:i-1])+1:sum(N_points[:i]),:] * y_MC_prec) * y_MC_pred[:,i];'''
    
    model_code += '''
            log_lik[i] = multi_normal_lpdf(y1[sum(N_points[:i-1])+1:sum(N_points[:i])] | y_pred[sum(N_points[:i-1])+1:sum(N_points[:i])], cov_y);
        }

        for (i in 1:N_unknown) {
            for (t in 1:N_T) {
                for (m in 1:M-1) {
                    y_MC_pred[m+N_C*(t-1), N_known+i] = dot_product(U_raw[t,m,:,Idx_all[N_known+i,1]] .* v_ARD, V_raw[t,m,:,Idx_all[N_known+i,2]]);
                    y_MC_pred[N_C-m+1+N_C*(t-1), N_known+i] = dot_product(U_raw[t,m,:,Idx_all[N_known+i,2]] .* v_ARD, V_raw[t,m,:,Idx_all[N_known+i,1]]); 
                }
                y_MC_pred[M+N_C*(t-1), N_known+i] = dot_product(U_raw[t,M,:,Idx_all[N_known+i,1]] .* v_ARD, U_raw[t,M,:,Idx_all[N_known+i,2]]);
            }
        }
    }
    '''

    return model_code