from spinqit.qiskit.circuit import QuantumCircuit
from math import pi

# Circuito de Bell (estilo Qiskit) sobre el backend NMR
circuit = QuantumCircuit(2)
circuit.h(0)
circuit.rx(pi, 1)
circuit.cx(0, 1)

# Opcionales (si se omiten, compiler se deduce y shots=1024)
compiler = "qiskit"
shots = 1024
