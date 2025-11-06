package br.ufal.ic.easy;

import br.ufal.ic.easy.operations.Operation;
import br.ufal.ic.easy.operations.Sum;

public class Calculator {

    public Calculator() { }

    public int sum(int a, int b) {
        Operation sum = new Sum();
        return sum.execute(a, b);
    }

}