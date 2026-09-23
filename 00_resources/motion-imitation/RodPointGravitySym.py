import sympy as sp

# Define symbols
G, lambda_mass, L = sp.symbols('G lambda_mass L')
x_p, y_p, z_p, l = sp.symbols('x_p y_p z_p l')
a, b, c = sp.symbols('a b c')

# Define the integrand functions
scale =  ((x_p - a * l) ** 2 + (y_p - b * l) ** 2 + (z_p - c * l) ** 2) ** (3 / 2)
Fx_integrand = (x_p - a * l) / scale
Fy_integrand = (y_p - b * l) / scale
Fz_integrand = (z_p - c * l) / scale

# Perform the integration
Fx_integral = sp.integrate(Fx_integrand, (l, 0, L))
Fy_integral = sp.integrate(Fy_integrand, (l, 0, L))
Fz_integral = sp.integrate(Fz_integrand, (l, 0, L))

sp.pprint(Fx_integral)
sp.pprint(Fy_integral)
sp.pprint(Fz_integral)
# Total gravitational force components
Fx_total = -G * lambda_mass * Fx_integral
Fy_total = -G * lambda_mass * Fy_integral
Fz_total = -G * lambda_mass * Fz_integral

# Substitute values for G, lambda_mass, L, x_p, y_p, and z_p
values = {
    G: 6.67430e-11,
    lambda_mass: 0.5,
    L: 2.0,
    x_p: 1.0,
    y_p: 1.0,
    z_p: 1.0
}

Fx_total_val = Fx_total.evalf(subs=values)
Fy_total_val = Fy_total.evalf(subs=values)
Fz_total_val = Fz_total.evalf(subs=values)

print(Fx_total_val, Fy_total_val, Fz_total_val)
