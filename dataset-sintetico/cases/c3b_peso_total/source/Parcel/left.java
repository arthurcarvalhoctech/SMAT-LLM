package demo;

public class Parcel {
    public int a = 60;
    public int count = 1;
    public int b = 40;
    public boolean big;

    public void check() {
        big = a + b > 100;
    }
}
