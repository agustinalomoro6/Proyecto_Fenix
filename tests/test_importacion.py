"""Comprueba que todo el paquete se pueda importar; integrante 1."""
import importlib
import pkgutil

import pytest

import fenix

MODULOS = [info.name for info in pkgutil.walk_packages(fenix.__path__, "fenix.")]


@pytest.mark.parametrize("nombre", MODULOS)
def test_modulo_se_importa(nombre):
    """Un error de sintaxis o de importación en cualquier módulo hace fallar el test."""
    importlib.import_module(nombre)


def test_jerarquia_de_excepciones():
    """Las excepciones del dominio heredan de ProjectError y esta de Exception."""
    errors = importlib.import_module("fenix.utils.errors")
    assert issubclass(errors.ProjectError, Exception)
    for clase in (errors.ValidationError, errors.RetryableError, errors.PermanentError):
        assert issubclass(clase, errors.ProjectError)
