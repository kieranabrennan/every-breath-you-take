

def exp_moving_average(prev_mean, value, alpha):
    return alpha*prev_mean + (1-alpha)*value