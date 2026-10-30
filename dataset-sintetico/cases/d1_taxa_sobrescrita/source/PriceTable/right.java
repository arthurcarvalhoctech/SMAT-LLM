package demo;

public class PriceTable {
    public int total;

    public void quote(int qty) {
        int rate = 5;
        int fee = 1;
        rate = 20;
        total = qty * rate + fee;
    }
}
