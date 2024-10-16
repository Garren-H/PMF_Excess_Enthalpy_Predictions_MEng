
    functions {
        vector NRTL(vector x, vector T, vector p12, vector p21, real a, matrix map_tij, matrix map_tij_dT) {
            int N = rows(x);
            vector[N] t12 = map_tij * p12;
            vector[N] t21 = map_tij * p21;
            vector[N] dt12_dT = map_tij_dT * p12;
            vector[N] dt21_dT = map_tij_dT * p21;   
            vector[N] at12 = a * t12;
            vector[N] at21 = a * t21;
            vector[N] G12 = exp(-at12);
            vector[N] G21 = exp(-at21);
            vector[N] term1 = ( ( (1-x) .* G12 .* (1 - at12) + x .* square(G12) ) ./ square((1-x) + x .* G12) ) .* dt12_dT;
            vector[N] term2 = ( ( x .* G21 .* (1 - at21) + (1-x) .* square(G21) ) ./ square(x + (1-x) .* G21) ) .* dt21_dT;
            return -8.314 * square(T) .* x .* (1-x) .* ( term1 + term2 );
        }

        real ps_like(array[] int N_slice, int start, int end, vector y, vector x, vector T, array[] matrix U_raw, 
          array[] matrix V_raw, vector v_ARD, vector v, vector scaling, real a, real error, array[] int N_points, 
          array[,] int Idx_known, array[] matrix mapping, 
          vector var_data, int D) {
            real all_target = 0;
            for (i in start:end) {
                vector[4] p12_raw;
                vector[4] p21_raw;
                vector[N_points[i]] y_std = sqrt(var_data[sum(N_points[:i-1])+1:sum(N_points[:i])]+v[i]);
                vector[N_points[i]] y_means;

                for (j in 1:4) {
                    vector[D] ui = U_raw[j,:,Idx_known[i,1]] .* v_ARD;
                    vector[D] vj = V_raw[j,:,Idx_known[i,2]];
                    vector[D] uj = U_raw[j,:,Idx_known[i,2]] .* v_ARD;
                    vector[D] vi = V_raw[j,:,Idx_known[i,1]];
                    p12_raw[j] = dot_product(ui, vj);
                    p21_raw[j] = dot_product(uj, vi);
                }

                y_means = NRTL(x[sum(N_points[:i-1])+1:sum(N_points[:i])], 
                                T[sum(N_points[:i-1])+1:sum(N_points[:i])], 
                                p12_raw, p21_raw, a,
                                mapping[1][sum(N_points[:i-1])+1:sum(N_points[:i]),:],
                                mapping[2][sum(N_points[:i-1])+1:sum(N_points[:i]),:]);
                all_target += normal_lpdf(y[sum(N_points[:i-1])+1:sum(N_points[:i])] | y_means, y_std);
            }
            return all_target;
        }
    }

    data {
        int<lower=1> N_known;                       // number of known data points
        array[N_known] int<lower=1> N_points;       // number of data points in each known data set
        vector[sum(N_points)] x;                    // mole fraction
        vector[sum(N_points)] T;                    // temperature
        vector[sum(N_points)] y;                    // excess enthalpy
        vector<lower=0>[4] scaling;                 // scaling factor for NRTL parameter
        real<lower=0> a;                            // alpha value for NRTL model
        int<lower=1> grainsize;                     // grainsize for parallelization
        int<lower=1> N;                             // number of compounds
        int<lower=1,upper=N> D;                     // number of features
        array[N_known,2] int<lower=1> Idx_known;    // indices of known data points
        real<lower=0>scale_cauchy;                  // prior scale for cauchy distribution
        vector<lower=0>[N_known] v;                 // known data-model variance

        real<lower=0> sigma_zeros;                  // soft-constraint for pure compounds
        int N_x_zeros;                              // number of compositions to evaluate at zero
        int N_T_zeros;                              // number of temperatures to evaluate at zero
        vector[N_x_zeros] x_zeros;                  // mole fraction at zero
        vector[N_T_zeros] T_zeros;                  // temperature at zero
    }

    transformed data {
        real error = 0.01;                                                  // error in the data (fraction of experimental data)
        vector[sum(N_points)] var_data = square(error*y);                   // variance of the data
        array[2] matrix[sum(N_points),4] mapping;                           // temperature mapping
        array[N_known] int N_slice;                                         // slice indices for parallelization
        vector[N_x_zeros*N_T_zeros] x_zeros_all;                            // all compositions at zero
        vector[N_x_zeros*N_T_zeros] T_zeros_all;                            // all temperatures at zero
        array[2] matrix[N_x_zeros*N_T_zeros,4] mapping_zeros;               // mapping for zeros

        for (i in 1:N_T_zeros) {
            x_zeros_all[(i-1)*N_x_zeros+1:i*N_x_zeros] = x_zeros;
            T_zeros_all[(i-1)*N_x_zeros+1:i*N_x_zeros] = rep_vector(T_zeros[i], N_x_zeros);
        }
        mapping_zeros[1] = append_col(append_col(append_col(rep_vector(1.0, N_x_zeros*N_T_zeros), T_zeros_all), 
                        1.0 ./ T_zeros_all), log(T_zeros_all));
        mapping_zeros[1] = mapping_zeros[1] .* rep_matrix(scaling', N_x_zeros*N_T_zeros);
        mapping_zeros[2] = append_col(append_col(append_col(rep_vector(0.0, N_x_zeros*N_T_zeros), rep_vector(1.0, N_x_zeros*N_T_zeros)),
                        -1.0 ./ square(T_zeros_all)), 1.0 ./ T_zeros_all);
        mapping_zeros[2] = mapping_zeros[2] .* rep_matrix(scaling', N_x_zeros*N_T_zeros);
        
        for (i in 1:N_known) {
            N_slice[i] = i;
        }

        mapping[1] = append_col(append_col(append_col(rep_vector(1.0, sum(N_points)), T),
                        1.0 ./ T), log(T));         // mapping for tij
        mapping[1] = mapping[1] .* rep_matrix(scaling', sum(N_points)); // scaling the mapping

        mapping[2] = append_col(append_col(append_col(rep_vector(0.0, sum(N_points)), rep_vector(1.0, sum(N_points))),
                        -1.0 ./ square(T)), 1.0 ./ T);    // mapping for dtij_dT
        mapping[2] = mapping[2] .* rep_matrix(scaling', sum(N_points)); // scaling the mapping
    }

    parameters {
        array[4] matrix[D,N] U_raw;                 // feature matrices U
        array[4] matrix[D,N] V_raw;                 // feature matrices V
        vector[D] v_ARD_raw;                        // ARD variances
    }

    transformed parameters {
        vector[D] v_ARD = cumulative_sum(exp(v_ARD_raw)); // ARD variances with odering constraints
    }
    
    model {
        // half-cauhcy prior for ARD variances of the feature matrices
        v_ARD ~ cauchy(0, scale_cauchy);
        target += sum(v_ARD_raw); // jacobian adjustment

        // prior on feature matrices
        for (i in 1:4) {
            to_vector(U_raw[i]) ~ std_normal();
            to_vector(V_raw[i]) ~ std_normal();
        }
        
        // Likelihood function
        target += reduce_sum(ps_like, N_slice, grainsize, y, x, T, U_raw, 
                                V_raw, v_ARD, v, scaling, a, error, N_points, 
                                Idx_known, mapping, 
                                var_data, D);
        
        
        // Likelihood for zeros
        {
            vector[N_x_zeros*N_T_zeros*N] y_zeros;
            for (i in 1:N) {
                vector[4] p_pure;
                for (j in 1:4) {
                    vector[D] ui = U_raw[j,:,i] .* v_ARD;
                    vector[D] vi = V_raw[j,:,i];
                    p_pure[j] = dot_product(ui, vi);
                }
                y_zeros[(i-1)*N_x_zeros*N_T_zeros+1:i*N_x_zeros*N_T_zeros] = NRTL(x_zeros_all, T_zeros_all, p_pure, p_pure, a, mapping_zeros[1], mapping_zeros[2]);
            }
            y_zeros ~ normal(0, sigma_zeros);
        }
    }

    generated quantities {
        vector[N_known] log_lik;
        for (i in 1:N_known) {
            log_lik[i] = ps_like(N_slice, i, i, y, x, T, U_raw, V_raw, v_ARD, v, scaling, a, error, 
                                N_points, Idx_known, mapping, var_data, D);
        
        }
    }
    