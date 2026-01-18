// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20 {
    function transfer(address, uint256) external returns (bool);
    function transferFrom(address, address, uint256) external returns (bool);
}

interface IRewarder {
    function onSwap(address swapper, uint256 amountIn) external;
}

contract SimpleCPAMM {
    address public immutable token0;
    address public immutable token1;

    uint16 public immutable feeBps; // e.g. 30 = 0.30%
    address public immutable feeCollector;
    address public immutable rewarder;

    uint256 public reserve0;
    uint256 public reserve1;

    event LiquidityAdded(address indexed provider, uint256 amount0, uint256 amount1);
    event Swap(address indexed trader, address indexed tokenIn, uint256 amountIn, address indexed tokenOut, uint256 amountOut, uint256 feePaid);

    constructor(address token0_, address token1_, uint16 feeBps_, address feeCollector_, address rewarder_) {
        require(token0_ != address(0) && token1_ != address(0), "BAD_TOKEN");
        require(feeBps_ <= 10_000, "BAD_FEE");
        require(feeCollector_ != address(0), "BAD_COLLECTOR");
        token0 = token0_;
        token1 = token1_;
        feeBps = feeBps_;
        feeCollector = feeCollector_;
        rewarder = rewarder_;
    }

    function addLiquidity(uint256 amount0, uint256 amount1) external {
        require(amount0 > 0 && amount1 > 0, "BAD_AMOUNTS");
        require(IERC20(token0).transferFrom(msg.sender, address(this), amount0), "T0_XFER");
        require(IERC20(token1).transferFrom(msg.sender, address(this), amount1), "T1_XFER");
        reserve0 += amount0;
        reserve1 += amount1;
        emit LiquidityAdded(msg.sender, amount0, amount1);
    }

    function swap0For1(uint256 amount0In) external returns (uint256 amount1Out) {
        require(amount0In > 0, "BAD_IN");
        require(IERC20(token0).transferFrom(msg.sender, address(this), amount0In), "T0_IN");

        uint256 feePaid = (amount0In * feeBps) / 10_000;
        uint256 amount0Effective = amount0In - feePaid;
        require(IERC20(token0).transfer(feeCollector, feePaid), "FEE_XFER");

        amount1Out = _getAmountOut(amount0Effective, reserve0, reserve1);
        reserve0 += amount0Effective;
        reserve1 -= amount1Out;
        require(IERC20(token1).transfer(msg.sender, amount1Out), "T1_OUT");
        emit Swap(msg.sender, token0, amount0In, token1, amount1Out, feePaid);
        _onSwap(amount0In);
    }

    function swap1For0(uint256 amount1In) external returns (uint256 amount0Out) {
        require(amount1In > 0, "BAD_IN");
        require(IERC20(token1).transferFrom(msg.sender, address(this), amount1In), "T1_IN");

        uint256 feePaid = (amount1In * feeBps) / 10_000;
        uint256 amount1Effective = amount1In - feePaid;
        require(IERC20(token1).transfer(feeCollector, feePaid), "FEE_XFER");

        amount0Out = _getAmountOut(amount1Effective, reserve1, reserve0);
        reserve1 += amount1Effective;
        reserve0 -= amount0Out;
        require(IERC20(token0).transfer(msg.sender, amount0Out), "T0_OUT");
        emit Swap(msg.sender, token1, amount1In, token0, amount0Out, feePaid);
        _onSwap(amount1In);
    }

    function _getAmountOut(uint256 amountIn, uint256 reserveIn, uint256 reserveOut) internal pure returns (uint256) {
        // Classic constant product swap: out = (reserveOut * amountIn) / (reserveIn + amountIn)
        require(reserveIn > 0 && reserveOut > 0, "NO_LIQ");
        return (reserveOut * amountIn) / (reserveIn + amountIn);
    }

    function _onSwap(uint256 amountIn) internal {
        if (rewarder != address(0)) {
            IRewarder(rewarder).onSwap(msg.sender, amountIn);
        }
    }
}

