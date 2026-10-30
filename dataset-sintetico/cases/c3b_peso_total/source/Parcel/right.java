package demo;

public class Parcel {
    public int a = 40;
    public int count = 1;
    public int b = 60;
    public boolean big;

    public void check() {
        big = a + b > 100;
    }
}
