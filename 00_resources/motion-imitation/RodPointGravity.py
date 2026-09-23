import numpy as np
from scipy.integrate import quad

# Constants
G = 6.67430e-11  # gravitational constant in m^3 kg^-1 s^-2

# Rod parameters
L = 2.0  # length of the rod in meters
lambda_mass = 0.5  # linear mass density of the rod in kg/m

# Point parameters
x_p = 1.0  # x-coordinate of the point in meters
y_p = 1.0  # y-coordinate of the point in meters
z_p = 1.0  # z-coordinate of the point in meters

# Integrand functions
def integrand_Fx(l, x_p, y_p, z_p):
    return (x_p - l) / ((x_p - l)**2 + y_p**2 + z_p**2)**(3/2)

def integrand_Fy(l, x_p, y_p, z_p):
    return y_p / ((x_p - l)**2 + y_p**2 + z_p**2)**(3/2)

def integrand_Fz(l, x_p, y_p, z_p):
    return z_p / ((x_p - l)**2 + y_p**2 + z_p**2)**(3/2)

# Perform the integration for each component
Fx, _ = quad(integrand_Fx, 0, L, args=(x_p, y_p, z_p))
Fy, _ = quad(integrand_Fy, 0, L, args=(x_p, y_p, z_p))
Fz, _ = quad(integrand_Fz, 0, L, args=(x_p, y_p, z_p))

# Total gravitational force components
Fx_total = -G * lambda_mass * Fx
Fy_total = -G * lambda_mass * Fy
Fz_total = -G * lambda_mass * Fz

print(Fx_total, Fy_total, Fz_total)
