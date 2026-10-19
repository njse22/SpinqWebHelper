from spinqit import Circuit, H, CX, Rx
from math import pi

# Circuito de Bell sobre el backend NMR (API nativa de SpinQit)
circuit = Circuit()
q = circuit.allocateQubits(2)
circuit << (Rx, q[0], pi)
circuit << (H, q[1])
circuit << (CX, (q[0], q[1]))

# Opcionales (si se omiten, compiler="native" y shots=1024)
compiler = "native"
shots = 1024
