package model

import (
	"math"
	"testing"
)

func config(mode string) Config {
	return Config{mode, 10.5, map[string]Profile{"cyprus": {40, 700}, "greece": {60, 350}, "italy": {80, 100}}}
}
func TestPolicyChangesWinner(t *testing.T) {
	e, c := config("energy"), config("carbon")
	if err := e.Validate(); err != nil {
		t.Fatal(err)
	}
	if e.Score("cyprus") != 100 || e.Score("italy") != 0 {
		t.Fatal("energy ordering")
	}
	if c.Score("italy") != 100 || c.Score("cyprus") != 0 {
		t.Fatal("carbon ordering")
	}
	if c.Score("missing") != 0 {
		t.Fatal("missing fallback")
	}
	if math.Abs(c.Cost(c.Regions["cyprus"])-0.0816666666667) > 1e-10 {
		t.Fatal("units")
	}
}
func TestEqualAndZeroCarbon(t *testing.T) {
	c := config("carbon")
	c.Regions = map[string]Profile{"a": {40, 0}, "b": {40, 0}}
	if err := c.Validate(); err != nil {
		t.Fatal(err)
	}
	if c.Score("a") != 100 || c.Score("b") != 100 {
		t.Fatal("equal costs")
	}
}
func TestInvalidInputs(t *testing.T) {
	for _, v := range []float64{-1, 0, math.NaN(), math.Inf(1)} {
		c := config("energy")
		c.Seconds = v
		if c.Validate() == nil {
			t.Fatal("accepted invalid duration")
		}
	}
	c := config("carbon")
	c.Regions["x"] = Profile{40, -1}
	if c.Validate() == nil {
		t.Fatal("negative carbon")
	}
	c = config("bogus")
	if c.Validate() == nil {
		t.Fatal("invalid mode")
	}
}
