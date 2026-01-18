// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20Like {
    function balanceOf(address) external view returns (uint256);
    function transfer(address, uint256) external returns (bool);
}

contract FeeCollector {
    address public immutable dao;
    address public immutable manager;
    uint16 public immutable managerFeeBps; // e.g. 5000 = 50%

    constructor(address dao_, address manager_, uint16 managerFeeBps_) {
        require(dao_ != address(0) && manager_ != address(0), "BAD_ADDR");
        require(managerFeeBps_ <= 10_000, "BAD_BPS");
        dao = dao_;
        manager = manager_;
        managerFeeBps = managerFeeBps_;
    }

    function distribute(address token) external {
        uint256 bal = IERC20Like(token).balanceOf(address(this));
        if (bal == 0) return;

        uint256 managerCut = (bal * managerFeeBps) / 10_000;
        uint256 daoCut = bal - managerCut;

        if (managerCut > 0) {
            require(IERC20Like(token).transfer(manager, managerCut), "MANAGER_XFER");
        }
        if (daoCut > 0) {
            require(IERC20Like(token).transfer(dao, daoCut), "DAO_XFER");
        }
    }
}

